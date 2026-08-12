import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    APPROVAL_CHAIN,
    ContractStatus,
    ContractType,
    WorkflowAssigneeMode,
    WorkflowTargetType,
    form_chain,
)
from app.db.session import SessionLocal
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.workflow import WorkflowInstance
from app.services.workflow_catalog import WORKFLOW_DEFINITIONS
from app.services.workflow_engine import (
    WorkflowValidationError,
    eligible_designated_users,
    materialize_legacy_workflow,
)


WORKFLOW_BY_TARGET = {
    definition.target_type: definition for definition in WORKFLOW_DEFINITIONS
}

POSITION_BY_LEGACY_ROLE = {
    "business_handler": "supply.business_handler",
    "business_reviewer": "supply.business_reviewer",
    "finance_handler": "supply.finance_handler",
    "scm_director": "supply.company_leader",
    "legal_counsel": "external.legal_counsel",
    "risk_auditor": "investment.duty.supply_risk_review",
    "finance_reviewer": "investment.duty.supply_finance_review",
    "invest_director": "governance.supply_leader",
}


def _target_type(form_type: ContractType) -> WorkflowTargetType:
    if form_type == ContractType.PAYMENT:
        return WorkflowTargetType.PAYMENT_APPROVAL
    return WorkflowTargetType.BUSINESS_APPROVAL


def _legacy_rows(db: Session):
    contracts = list(db.scalars(
        select(Contract)
        .where(
            Contract.workflow_instance_id.is_(None),
            Contract.status.in_((
                ContractStatus.PENDING,
                ContractStatus.APPROVED,
                ContractStatus.REJECTED,
            )),
        )
        .order_by(Contract.id)
    ))
    forms = list(db.scalars(
        select(ApprovalForm)
        .where(
            ApprovalForm.workflow_instance_id.is_(None),
            ApprovalForm.status.in_((
                ContractStatus.PENDING,
                ContractStatus.APPROVED,
                ContractStatus.REJECTED,
            )),
        )
        .order_by(ApprovalForm.id)
    ))
    return [
        (WorkflowTargetType.CONTRACT, item, APPROVAL_CHAIN)
        for item in contracts
    ] + [
        (_target_type(item.form_type), item, form_chain(item.form_type))
        for item in forms
    ]


def _historical_item(target_type, target, legacy_chain):
    expected_role = (
        legacy_chain[target.current_step].value
        if 0 <= target.current_step < len(legacy_chain)
        else None
    )
    return {
        "target_type": target_type.value,
        "target_id": target.id,
        "current_step": target.current_step,
        "expected_role": expected_role,
        "classification": "historical_only",
        "admin_action": "retain version 1 history; do not materialize",
        "outcome": "historical_only",
    }, {}


def _pending_item(db, target_type, target, legacy_chain, as_of):
    if db.scalar(select(WorkflowInstance.id).where(
        WorkflowInstance.target_type == target_type,
        WorkflowInstance.target_id == target.id,
    )) is not None:
        return {
            "target_type": target_type.value,
            "target_id": target.id,
            "current_step": target.current_step,
            "expected_role": None,
            "classification": "invalid_state",
            "admin_action": "repair the missing target workflow instance link",
            "outcome": "invalid_state",
        }, {}
    if not 0 <= target.current_step < len(legacy_chain):
        return {
            "target_type": target_type.value,
            "target_id": target.id,
            "current_step": target.current_step,
            "expected_role": None,
            "classification": "invalid_state",
            "admin_action": "repair current_step against the version 1 chain",
            "outcome": "invalid_state",
        }, {}

    expected_role = legacy_chain[target.current_step].value
    definition = WORKFLOW_BY_TARGET[target_type]
    current_node = definition.nodes[target.current_step]
    expected_position = POSITION_BY_LEGACY_ROLE[expected_role]
    if current_node.position_code != expected_position:
        return {
            "target_type": target_type.value,
            "target_id": target.id,
            "current_step": target.current_step,
            "expected_role": expected_role,
            "classification": "invalid_state",
            "admin_action": "repair the version 1 step to version 2 position mapping",
            "outcome": "invalid_state",
        }, {}
    if current_node.mode != WorkflowAssigneeMode.SHARED_POSITION.value:
        return {
            "target_type": target_type.value,
            "target_id": target.id,
            "current_step": target.current_step,
            "expected_role": expected_role,
            "classification": "needs_designation",
            "admin_action": f"designate the current node {current_node.code} manually",
            "outcome": "needs_designation",
        }, {}

    designated_assignment_ids = {}
    selected_user_ids = set()
    unresolved_nodes = []
    for node in definition.nodes[target.current_step + 1:]:
        if node.mode != WorkflowAssigneeMode.DESIGNATED_USER.value:
            continue
        candidates = eligible_designated_users(
            db, definition.code, node.code, as_of
        )
        if len(candidates) != 1:
            unresolved_nodes.append(f"{node.code} ({len(candidates)} eligible)")
            continue
        candidate = candidates[0]
        if candidate.user_id == target.created_by or candidate.user_id in selected_user_ids:
            unresolved_nodes.append(f"{node.code} (duplicate workflow actor)")
            continue
        selected_user_ids.add(candidate.user_id)
        designated_assignment_ids[node.code] = candidate.assignment_id

    if unresolved_nodes:
        return {
            "target_type": target_type.value,
            "target_id": target.id,
            "current_step": target.current_step,
            "expected_role": expected_role,
            "classification": "needs_designation",
            "admin_action": "resolve designation: " + ", ".join(unresolved_nodes),
            "outcome": "needs_designation",
        }, {}
    return {
        "target_type": target_type.value,
        "target_id": target.id,
        "current_step": target.current_step,
        "expected_role": expected_role,
        "classification": "mappable_shared",
        "admin_action": "run apply migration",
        "outcome": "not_applied",
    }, designated_assignment_ids


def _race_outcome(db: Session, target_type: WorkflowTargetType, target_id: int) -> str:
    instance_id = db.scalar(select(WorkflowInstance.id).where(
        WorkflowInstance.target_type == target_type,
        WorkflowInstance.target_id == target_id,
    ))
    target_model = Contract if target_type == WorkflowTargetType.CONTRACT else ApprovalForm
    linked_instance_id = db.scalar(select(target_model.workflow_instance_id).where(
        target_model.id == target_id
    ))
    if instance_id is not None and linked_instance_id == instance_id:
        return "already_migrated"
    return "invalid_state"


def _apply_failure_outcome(
    db: Session,
    item: dict,
    target_type: WorkflowTargetType,
    target_id: int,
    error: WorkflowValidationError,
) -> None:
    if error.code in {"workflow_already_started", "legacy_workflow_not_migratable"}:
        item["outcome"] = _race_outcome(db, target_type, target_id)
        item["admin_action"] = (
            "verify concurrently migrated workflow instance"
            if item["outcome"] == "already_migrated"
            else "repair concurrent or unlinked workflow instance state"
        )
    elif error.code == "workflow_catalog_drift":
        item["outcome"] = "invalid_state"
        item["admin_action"] = "repair published workflow catalog drift before apply"
    else:
        item["outcome"] = "needs_designation"
        item["admin_action"] = f"rerun dry-run after migration validation: {error.code}"


def migrate_active_workflows(
    db: Session,
    *,
    apply: bool = False,
    as_of: date | None = None,
    migrated_at: datetime | None = None,
) -> dict:
    as_of = as_of or date.today()
    migrated_at = migrated_at or datetime.now()
    items = []
    migrated = 0
    with db.no_autoflush:
        rows = _legacy_rows(db)
        for target_type, target, legacy_chain in rows:
            if target.status in (ContractStatus.APPROVED, ContractStatus.REJECTED):
                item, assignments = _historical_item(
                    target_type, target, legacy_chain
                )
            else:
                item, assignments = _pending_item(
                    db, target_type, target, legacy_chain, as_of
                )
            if apply and item["classification"] == "mappable_shared":
                try:
                    materialize_legacy_workflow(
                        db,
                        target_type,
                        target.id,
                        target.current_step,
                        assignments,
                        migrated_at,
                        as_of,
                    )
                except WorkflowValidationError as error:
                    _apply_failure_outcome(
                        db, item, target_type, target.id, error
                    )
                else:
                    item["outcome"] = "migrated"
                    item["admin_action"] = "verify migrated workflow instance"
                    migrated += 1
            items.append(item)
    classification_counts = Counter(item["classification"] for item in items)
    outcome_counts = Counter(item["outcome"] for item in items)
    unresolved = sum(
        outcome_counts[outcome]
        for outcome in ("needs_designation", "invalid_state")
    )
    return {
        "mode": "apply" if apply else "dry-run",
        "as_of": as_of.isoformat(),
        "items": items,
        "classification_counts": dict(sorted(classification_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "migrated": migrated,
        "unresolved": unresolved,
    }


class ReportFinalizeError(OSError):
    pass


def _write_report_temp(report_path: Path, report: dict, temp_path: Path | None = None) -> Path:
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if temp_path is None:
        descriptor, name = tempfile.mkstemp(
            prefix=f"{report_path.name}.", suffix=".tmp", dir=report_path.parent
        )
        temp_path = Path(name)
    else:
        descriptor = os.open(temp_path, os.O_WRONLY | os.O_TRUNC)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return temp_path


def save_active_workflow_migration_report(
    db: Session,
    report_path: str | Path,
    *,
    apply: bool = False,
    as_of: date | None = None,
    migrated_at: datetime | None = None,
) -> dict:
    report_path = Path(report_path)
    preview = migrate_active_workflows(db, apply=False, as_of=as_of)
    json.dumps(preview, ensure_ascii=False, indent=2)
    temp_path = _write_report_temp(report_path, preview)
    committed = False
    try:
        report = migrate_active_workflows(
            db,
            apply=apply,
            as_of=as_of,
            migrated_at=migrated_at,
        )
        _write_report_temp(report_path, report, temp_path)
        if apply:
            db.commit()
            committed = True
        else:
            db.rollback()
        try:
            os.replace(temp_path, report_path)
        except OSError as error:
            if committed:
                raise ReportFinalizeError(
                    f"database committed; recover report from temporary file: {temp_path}"
                ) from error
            raise
        return report
    except Exception:
        if not committed:
            db.rollback()
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify or safely materialize active legacy workflows."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", default="active-workflow-migration.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    with SessionLocal() as db:
        try:
            report = save_active_workflow_migration_report(
                db, args.report, apply=args.apply
            )
        except Exception as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["unresolved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
