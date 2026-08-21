from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.enums import AssignmentStatus, PositionCategory
from app.db import init_db  # noqa: F401
from app.db.base import Base
from app.models.contract import Contract
from app.models.legal_risk import LegalCase
from app.models.organization import Organization, Position, PositionPermission, UserAssignment
from app.models.user import User
from app.models.workflow import WorkflowDefinition, WorkflowInstance, WorkflowTask, WorkflowTaskAction
from scripts.migrate_legal_contract_authorization import apply_migration, build_report


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def publisher(db):
    user = User(
        username="publisher",
        full_name="Publisher",
        hashed_password="test",
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def legacy_contract(db, publisher):
    contract = Contract(
        contract_no="LEGACY-001",
        title="Legacy contract",
        created_by=publisher.id,
        company_code="",
        organization_code="",
        workflow_route_version=0,
    )
    db.add(contract)
    db.commit()
    return contract


@pytest.fixture
def legacy_case(db, publisher):
    case = LegalCase(
        case_name="Legacy case",
        created_by=publisher.id,
        company_code="",
        organization_code="",
    )
    db.add(case)
    db.commit()
    return case


def test_migration_preview_reports_backfill_without_writing(
    db, legacy_contract, legacy_case
):
    report = build_report(db)

    assert report["ownership_backfill"] == {
        "contracts": 1,
        "cases": 1,
    }
    assert legacy_contract.company_code == ""
    assert legacy_case.company_code == ""
    assert db.query(Organization).count() == 0
    assert db.query(WorkflowDefinition).count() == 0


def test_migration_apply_is_idempotent(
    db, legacy_contract, legacy_case, publisher
):
    first = apply_migration(db, publisher.id)
    definition_counts = (
        db.query(WorkflowDefinition).count(),
        sum(len(item.versions) for item in db.query(WorkflowDefinition)),
    )
    second = apply_migration(db, publisher.id)

    assert first["blocking_issues"] == []
    assert second["ownership_backfill"] == {"contracts": 0, "cases": 0}
    assert legacy_contract.company_code == "supplymanagement"
    assert legacy_contract.organization_code == "supplymanagement"
    assert legacy_contract.workflow_route_version == 0
    assert legacy_case.company_code == "investment"
    assert legacy_case.organization_code == "investment.legal_risk"
    assert definition_counts == (3, 3)
    assert (
        db.query(WorkflowDefinition).count(),
        sum(len(item.versions) for item in db.query(WorkflowDefinition)),
    ) == definition_counts


def test_report_has_required_sections_and_missing_publisher_blocks_apply(
    db, legacy_contract, legacy_case, publisher
):
    publisher.is_active = False
    db.commit()

    preview = build_report(db)
    applied = apply_migration(db, publisher.id)

    assert set(preview) == {
        "organizations",
        "positions",
        "permissions",
        "ownership_backfill",
        "workflow_versions",
        "blocking_issues",
    }
    assert any(item["code"] == "missing_superuser_publisher" for item in preview["blocking_issues"])
    assert applied["blocking_issues"]
    assert legacy_contract.company_code == ""
    assert legacy_case.company_code == ""


def test_catalog_conflict_and_ambiguous_active_assignment_block_apply(
    db, legacy_contract, publisher
):
    conflicting = Organization(
        code="investment",
        name="Wrong type",
        organization_type="external",
        company_code=None,
    )
    db.add(conflicting)
    positions = []
    for code in (
        "investment.executive.general_manager",
        "investment.executive.chairman",
    ):
        position = Position(
            code=code,
            name=code,
            category=PositionCategory.EXECUTIVE,
        )
        db.add(position)
        positions.append(position)
    db.flush()
    for position in positions:
        db.add(UserAssignment(
            user_id=publisher.id,
            organization_id=conflicting.id,
            position_id=position.id,
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        ))
    db.commit()

    report = apply_migration(db, publisher.id)

    codes = {item["code"] for item in report["blocking_issues"]}
    assert "organization_catalog_conflict" in codes
    assert "workflow_assignment_conflict" in codes
    assert legacy_contract.company_code == ""


def test_repeat_apply_does_not_restore_removed_position_permission(db, publisher):
    first = apply_migration(db, publisher.id)
    assert first["blocking_issues"] == []
    removed = db.scalar(select(PositionPermission).order_by(PositionPermission.id))
    assert removed is not None
    removed_identity = (
        removed.position_id,
        removed.permission_id,
        removed.data_scope,
        removed.scope_ref,
    )
    db.delete(removed)
    db.commit()

    second = apply_migration(db, publisher.id)

    assert second["blocking_issues"] == []
    assert db.scalar(select(PositionPermission).where(
        PositionPermission.position_id == removed_identity[0],
        PositionPermission.permission_id == removed_identity[1],
        PositionPermission.data_scope == removed_identity[2],
        PositionPermission.scope_ref == removed_identity[3],
    )) is None


def test_apply_does_not_rewrite_historical_workflow_runtime(db, publisher):
    before = (
        db.query(WorkflowInstance).count(),
        db.query(WorkflowTask).count(),
        db.query(WorkflowTaskAction).count(),
    )

    report = apply_migration(db, publisher.id)

    assert report["blocking_issues"] == []
    assert (
        db.query(WorkflowInstance).count(),
        db.query(WorkflowTask).count(),
        db.query(WorkflowTaskAction).count(),
    ) == before


def test_mysql_migration_guards_every_schema_change_and_backfills_before_constraints():
    source = Path(
        "migrations/20260821_legal_contract_organization_authorization.sql"
    ).read_text(encoding="utf-8")

    columns = {
        "biz_contract": (
            "company_code",
            "organization_code",
            "initiator_assignment_id",
            "workflow_route_version",
        ),
        "legal_case": (
            "company_code",
            "organization_code",
            "initiator_assignment_id",
        ),
        "wf_node": ("candidate_rule", "candidate_position_codes"),
    }
    for table_name, column_names in columns.items():
        for column_name in column_names:
            assert (
                f"table_name = '{table_name}' AND column_name = '{column_name}'"
                in source
            )
    assert "information_schema.statistics" in source
    assert "information_schema.table_constraints" in source
    assert "ADD COLUMN IF NOT EXISTS" not in source
    assert source.index("UPDATE `biz_contract`") < source.index(
        "MODIFY COLUMN `company_code` VARCHAR(64) NOT NULL"
    )
    assert source.index("UPDATE `legal_case`") < source.index(
        "MODIFY COLUMN `company_code` VARCHAR(64) NOT NULL"
    )
    assert "SET `workflow_route_version` = 0" in source
    for table_name in ("wf_instance", "wf_node", "wf_task", "wf_task_action"):
        assert f"UPDATE `{table_name}`" not in source
