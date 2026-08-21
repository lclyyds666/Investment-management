import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.enums import (
    WorkflowAssigneeMode,
    WorkflowVersionStatus,
)
from app.db.session import SessionLocal
from app.models.contract import Contract
from app.models.legal_risk import LegalCase
from app.models.organization import Organization, Permission, Position
from app.models.user import User
from app.models.workflow import WorkflowDefinition, WorkflowNode, WorkflowVersion
from app.services.organization_catalog import (
    ORGANIZATION_CATALOG,
    PERMISSION_CATALOG,
    POSITION_CATALOG,
    seed_authorization_catalog,
)
from app.services.workflow_catalog import WORKFLOW_DEFINITIONS
from app.services.workflow_engine import validate_workflow_version


LEGAL_WORKFLOW_DEFINITIONS = tuple(
    definition
    for definition in WORKFLOW_DEFINITIONS
    if definition.code.startswith("investment.contract.")
)


def _catalog_entries(db: Session):
    organizations = list(db.scalars(select(Organization)))
    organizations_by_code = {item.code: item for item in organizations}
    organization_codes_by_id = {item.id: item.code for item in organizations}
    organization_report = []
    blocking_issues = []
    for expected in ORGANIZATION_CATALOG:
        current = organizations_by_code.get(expected["code"])
        if current is None:
            status = "create"
        else:
            current_parent = organization_codes_by_id.get(current.parent_id)
            conflicts = {
                "organization_type": (
                    current.organization_type.value,
                    expected["type"],
                ),
                "parent": (current_parent, expected["parent"]),
                "company_code": (current.company_code, expected["company_code"]),
            }
            conflicts = {
                field: {"current": values[0], "expected": values[1]}
                for field, values in conflicts.items()
                if values[0] != values[1]
            }
            if conflicts:
                status = "conflict"
                blocking_issues.append({
                    "code": "organization_catalog_conflict",
                    "catalog_code": expected["code"],
                    "details": conflicts,
                })
            elif current.name != expected["name"]:
                status = "update"
            else:
                status = "unchanged"
        organization_report.append({"code": expected["code"], "status": status})

    positions_by_code = {
        item.code: item for item in db.scalars(select(Position))
    }
    position_report = []
    for expected in POSITION_CATALOG:
        current = positions_by_code.get(expected["code"])
        if current is None:
            status = "create"
        elif current.category.value != expected["category"]:
            status = "conflict"
            blocking_issues.append({
                "code": "position_catalog_conflict",
                "catalog_code": expected["code"],
                "details": {
                    "category": {
                        "current": current.category.value,
                        "expected": expected["category"],
                    }
                },
            })
        elif current.name != expected["name"]:
            status = "update"
        else:
            status = "unchanged"
        position_report.append({"code": expected["code"], "status": status})

    permissions_by_code = {
        item.code: item for item in db.scalars(select(Permission))
    }
    permission_report = []
    for expected in PERMISSION_CATALOG:
        current = permissions_by_code.get(expected["code"])
        if current is None:
            status = "create"
        else:
            conflicts = {
                "resource": (current.resource, expected["resource"]),
                "action": (current.action.value, expected["action"]),
            }
            conflicts = {
                field: {"current": values[0], "expected": values[1]}
                for field, values in conflicts.items()
                if values[0] != values[1]
            }
            if conflicts:
                status = "conflict"
                blocking_issues.append({
                    "code": "permission_catalog_conflict",
                    "catalog_code": expected["code"],
                    "details": conflicts,
                })
            elif current.name != expected["name"]:
                status = "update"
            else:
                status = "unchanged"
        permission_report.append({"code": expected["code"], "status": status})
    return organization_report, position_report, permission_report, blocking_issues


def _catalog_nodes(definition):
    return tuple(
        (
            sequence,
            item.code,
            item.name,
            item.position_code,
            item.mode,
            item.candidate_rule,
            item.candidate_position_codes,
            item.auto_complete_on_submit,
            item.allow_reject,
        )
        for sequence, item in enumerate(definition.nodes)
    )


def _persisted_nodes(version):
    return tuple(
        (
            item.sequence,
            item.code,
            item.name,
            item.position_code,
            item.assignee_mode.value,
            item.candidate_rule,
            tuple(item.candidate_position_codes or ()),
            item.auto_complete_on_submit,
            item.allow_reject,
        )
        for item in sorted(version.nodes, key=lambda node: node.sequence)
    )


def _workflow_entries(db: Session):
    report = []
    blocking_issues = []
    for expected in LEGAL_WORKFLOW_DEFINITIONS:
        current = db.execute(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.code == expected.code)
            .options(
                joinedload(WorkflowDefinition.versions)
                .joinedload(WorkflowVersion.nodes)
            )
        ).unique().scalar_one_or_none()
        status = "publish"
        if current is not None:
            if (
                current.name != expected.name
                or current.target_type != expected.target_type
            ):
                status = "conflict"
            else:
                version = next(
                    (item for item in current.versions if item.version == expected.version),
                    None,
                )
                if version is not None:
                    if (
                        version.status == WorkflowVersionStatus.PUBLISHED
                        and current.active_version_id == version.id
                        and _persisted_nodes(version) == _catalog_nodes(expected)
                    ):
                        status = "unchanged"
                    else:
                        status = "conflict"
        if status == "conflict":
            blocking_issues.append({
                "code": "workflow_catalog_conflict",
                "workflow_code": expected.code,
                "version": expected.version,
            })
        report.append({
            "code": expected.code,
            "version": expected.version,
            "status": status,
        })

        transient_nodes = []
        for sequence, item in enumerate(expected.nodes):
            position_codes = item.candidate_position_codes or (
                (item.position_code,) if item.position_code else ()
            )
            transient_nodes.extend(
                SimpleNamespace(
                    sequence=sequence,
                    code=item.code,
                    position_code=position_code,
                )
                for position_code in position_codes
            )
        transient_version = SimpleNamespace(nodes=transient_nodes)
        for issue in validate_workflow_version(db, transient_version):
            blocking_issues.append({
                "code": issue.code,
                "workflow_code": expected.code,
                "user_id": issue.user_id,
                "node_codes": list(issue.node_codes),
                "message": issue.message,
            })
    return report, blocking_issues


def _publisher_issue(db: Session, publisher_id: int | None):
    if publisher_id is None:
        publisher = db.scalar(
            select(User)
            .where(User.is_superuser.is_(True), User.is_active.is_(True))
            .order_by(User.id)
        )
    else:
        publisher = db.get(User, publisher_id)
    if (
        publisher is None
        or not publisher.is_superuser
        or not publisher.is_active
    ):
        return {
            "code": "missing_superuser_publisher",
            "publisher_id": publisher_id,
            "message": "An active superuser is required to publish workflows.",
        }
    return None


def build_report(db: Session, publisher_id: int | None = None) -> dict:
    organizations, positions, permissions, blocking_issues = _catalog_entries(db)
    workflow_versions, workflow_issues = _workflow_entries(db)
    blocking_issues.extend(workflow_issues)
    publisher_issue = _publisher_issue(db, publisher_id)
    if publisher_issue is not None:
        blocking_issues.append(publisher_issue)
    return {
        "organizations": organizations,
        "positions": positions,
        "permissions": permissions,
        "ownership_backfill": {
            "contracts": len(list(db.scalars(
                select(Contract.id).where(
                    (Contract.company_code.is_(None))
                    | (Contract.company_code == "")
                    | (Contract.organization_code.is_(None))
                    | (Contract.organization_code == "")
                )
            ))),
            "cases": len(list(db.scalars(
                select(LegalCase.id).where(
                    (LegalCase.company_code.is_(None))
                    | (LegalCase.company_code == "")
                    | (LegalCase.organization_code.is_(None))
                    | (LegalCase.organization_code == "")
                )
            ))),
        },
        "workflow_versions": workflow_versions,
        "blocking_issues": blocking_issues,
    }


def _publish_legal_workflows(db: Session, publisher_id: int) -> None:
    published_at = datetime.now()
    for expected in LEGAL_WORKFLOW_DEFINITIONS:
        definition = db.execute(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.code == expected.code)
            .options(
                joinedload(WorkflowDefinition.versions)
                .joinedload(WorkflowVersion.nodes)
            )
        ).unique().scalar_one_or_none()
        if definition is None:
            definition = WorkflowDefinition(
                code=expected.code,
                name=expected.name,
                target_type=expected.target_type,
            )
            db.add(definition)
            db.flush()
        version = next(
            (item for item in definition.versions if item.version == expected.version),
            None,
        )
        if version is not None:
            continue
        version = WorkflowVersion(
            definition_id=definition.id,
            version=expected.version,
            status=WorkflowVersionStatus.PUBLISHED,
            published_at=published_at,
            published_by=publisher_id,
        )
        db.add(version)
        db.flush()
        version.nodes = [
            WorkflowNode(
                sequence=sequence,
                code=item.code,
                name=item.name,
                position_code=item.position_code,
                assignee_mode=WorkflowAssigneeMode(item.mode),
                candidate_rule=item.candidate_rule,
                candidate_position_codes=list(item.candidate_position_codes),
                auto_complete_on_submit=item.auto_complete_on_submit,
                allow_reject=item.allow_reject,
            )
            for sequence, item in enumerate(expected.nodes)
        ]
        db.flush()
        definition.active_version_id = version.id


def apply_migration(db: Session, publisher_id: int) -> dict:
    report = build_report(db, publisher_id)
    if report["blocking_issues"]:
        return report
    try:
        seed_authorization_catalog(db)
        for contract in db.scalars(select(Contract).where(
            (Contract.company_code.is_(None))
            | (Contract.company_code == "")
            | (Contract.organization_code.is_(None))
            | (Contract.organization_code == "")
        )):
            contract.company_code = "supplymanagement"
            contract.organization_code = "supplymanagement"
        for case in db.scalars(select(LegalCase).where(
            (LegalCase.company_code.is_(None))
            | (LegalCase.company_code == "")
            | (LegalCase.organization_code.is_(None))
            | (LegalCase.organization_code == "")
        )):
            case.company_code = "investment"
            case.organization_code = "investment.legal_risk"
        _publish_legal_workflows(db, publisher_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return report


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.apply:
            publisher_id = db.scalar(
                select(User.id)
                .where(User.is_superuser.is_(True), User.is_active.is_(True))
                .order_by(User.id)
            )
            report = apply_migration(db, publisher_id or 0)
        else:
            report = build_report(db)
    _write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["blocking_issues"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
