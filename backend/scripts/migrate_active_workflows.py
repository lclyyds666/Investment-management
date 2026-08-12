import argparse
import json
from collections import Counter
from datetime import date, datetime

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
        "migrated": False,
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
            "migrated": False,
        }, {}
    if not 0 <= target.current_step < len(legacy_chain):
        return {
            "target_type": target_type.value,
            "target_id": target.id,
            "current_step": target.current_step,
            "expected_role": None,
            "classification": "invalid_state",
            "admin_action": "repair current_step against the version 1 chain",
            "migrated": False,
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
            "migrated": False,
        }, {}
    if current_node.mode != WorkflowAssigneeMode.SHARED_POSITION.value:
        return {
            "target_type": target_type.value,
            "target_id": target.id,
            "current_step": target.current_step,
            "expected_role": expected_role,
            "classification": "needs_designation",
            "admin_action": f"designate the current node {current_node.code} manually",
            "migrated": False,
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
            "migrated": False,
        }, {}
    return {
        "target_type": target_type.value,
        "target_id": target.id,
        "current_step": target.current_step,
        "expected_role": expected_role,
        "classification": "mappable_shared",
        "admin_action": "run apply migration",
        "migrated": False,
    }, designated_assignment_ids


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
                materialize_legacy_workflow(
                    db,
                    target_type,
                    target.id,
                    target.current_step,
                    assignments,
                    migrated_at,
                )
                item["migrated"] = True
                item["admin_action"] = "verify migrated workflow instance"
                migrated += 1
            items.append(item)
    counts = Counter(item["classification"] for item in items)
    unresolved = sum(
        counts[classification]
        for classification in ("needs_designation", "invalid_state")
    )
    return {
        "mode": "apply" if apply else "dry-run",
        "as_of": as_of.isoformat(),
        "items": items,
        "counts": dict(sorted(counts.items())),
        "migrated": migrated,
        "unresolved": unresolved,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify or safely materialize active legacy workflows."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", default="active-workflow-migration.json")
    args = parser.parse_args()
    with SessionLocal() as db:
        try:
            report = migrate_active_workflows(db, apply=args.apply)
            if args.apply:
                db.commit()
            else:
                db.rollback()
        except Exception:
            db.rollback()
            raise
    with open(args.report, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["unresolved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
