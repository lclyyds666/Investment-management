import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import init_db
from app.db.base import Base
from app.models.organization import (
    Organization,
    Permission,
    Position,
    PositionPermission,
    UserAssignment,
)
from app.models.user import User
from app.models.workflow import WorkflowDefinition, WorkflowVersion
from scripts.migrate_legal_contract_authorization import apply_migration


def _run_fresh_init(engine) -> None:
    session_factory = sessionmaker(bind=engine)
    with (
        patch.object(init_db, "engine", engine),
        patch.object(init_db, "SessionLocal", session_factory),
        patch.object(init_db, "seed_operation"),
        patch.object(init_db, "seed_customers"),
        patch.object(init_db, "seed_channels"),
        patch.object(init_db, "seed_scenic_configs"),
        patch.object(init_db, "seed_channel_data"),
        patch.object(init_db, "seed_invoices"),
    ):
        init_db.init()


def _canonical_authorization_snapshot(db: Session) -> dict:
    organizations = list(db.scalars(select(Organization)))
    organization_codes = {item.id: item.code for item in organizations}
    positions = list(db.scalars(select(Position)))
    position_codes = {item.id: item.code for item in positions}
    permissions = list(db.scalars(select(Permission)))
    permission_codes = {item.id: item.code for item in permissions}
    workflows = []
    for definition in db.scalars(
        select(WorkflowDefinition)
        .where(WorkflowDefinition.code.like("investment.contract.%"))
        .order_by(WorkflowDefinition.code)
    ):
        version = next(
            item
            for item in definition.versions
            if item.id == definition.active_version_id
        )
        workflows.append((
            definition.code,
            definition.name,
            definition.target_type.value,
            version.version,
            version.status.value,
            tuple(
                (
                    node.sequence,
                    node.code,
                    node.name,
                    node.position_code,
                    node.assignee_mode.value,
                    node.candidate_rule,
                    tuple(node.candidate_position_codes or ()),
                    node.auto_complete_on_submit,
                    node.allow_reject,
                )
                for node in sorted(version.nodes, key=lambda item: item.sequence)
            ),
        ))
    return {
        "organizations": tuple(sorted(
            (
                item.code,
                item.name,
                item.organization_type.value,
                organization_codes.get(item.parent_id),
                item.company_code,
                item.sort_order,
                item.is_active,
            )
            for item in organizations
        )),
        "positions": tuple(sorted(
            (item.code, item.name, item.category.value, item.is_active)
            for item in positions
        )),
        "permissions": tuple(sorted(
            (
                item.code,
                item.name,
                item.resource,
                item.action.value,
                item.is_active,
            )
            for item in permissions
        )),
        "grants": tuple(sorted(
            (
                position_codes[item.position_id],
                permission_codes[item.permission_id],
                item.data_scope.value,
                item.scope_ref,
            )
            for item in db.scalars(select(PositionPermission))
        )),
        "workflows": tuple(workflows),
    }


class DatabaseInitializationTest(unittest.TestCase):
    def test_init_creates_normalized_assignment_for_seeded_legacy_user(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        try:
            _run_fresh_init(engine)

            with Session(engine) as db:
                risk_user = db.scalar(select(User).where(User.username == "risk"))
                assignment = db.scalar(
                    select(UserAssignment).where(UserAssignment.user_id == risk_user.id)
                )

                self.assertEqual(
                    assignment.position.code,
                    "investment.duty.supply_risk_review",
                )
                self.assertEqual(assignment.source, "legacy")
                self.assertEqual(
                    db.query(WorkflowDefinition)
                    .filter(WorkflowDefinition.code.like("investment.contract.%"))
                    .count(),
                    3,
                )
                self.assertEqual(
                    db.query(WorkflowVersion)
                    .join(WorkflowVersion.definition)
                    .filter(WorkflowDefinition.code.like("investment.contract.%"))
                    .count(),
                    3,
                )
        finally:
            engine.dispose()

    def test_fresh_init_matches_legacy_explicit_apply_canonical_catalog(self):
        fresh_engine = create_engine("sqlite+pysqlite:///:memory:")
        legacy_engine = create_engine("sqlite+pysqlite:///:memory:")
        try:
            _run_fresh_init(fresh_engine)
            with Session(fresh_engine) as fresh_db:
                fresh_snapshot = _canonical_authorization_snapshot(fresh_db)

            Base.metadata.create_all(legacy_engine)
            with Session(legacy_engine) as legacy_db:
                init_db.seed_users(legacy_db)
                publisher = legacy_db.scalar(
                    select(User)
                    .where(User.is_superuser.is_(True), User.is_active.is_(True))
                    .order_by(User.id)
                )
                report = apply_migration(legacy_db, publisher.id)
                self.assertEqual(report["blocking_issues"], [])
                legacy_snapshot = _canonical_authorization_snapshot(legacy_db)

            self.assertEqual(fresh_snapshot, legacy_snapshot)
            self.assertEqual(len(fresh_snapshot["organizations"]), 10)
            self.assertEqual(len(fresh_snapshot["workflows"]), 3)
            self.assertTrue(fresh_snapshot["grants"])
        finally:
            fresh_engine.dispose()
            legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
