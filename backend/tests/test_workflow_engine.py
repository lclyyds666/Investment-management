import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.db.init_db  # noqa: F401
from app.core.enums import AssignmentStatus, PositionCategory, WorkflowVersionStatus
from app.db.base import Base
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from app.models.workflow import WorkflowDefinition, WorkflowNode, WorkflowVersion
from app.services.workflow_catalog import WORKFLOW_CATALOG
from app.services.workflow_engine import (
    WorkflowValidationError,
    ensure_workflow_version_mutable,
    seed_workflow_definitions,
    validate_workflow_version,
)


class WorkflowCatalogTest(unittest.TestCase):
    def test_contract_workflow_matches_confirmed_chain(self):
        nodes = WORKFLOW_CATALOG["supply.contract.v2"]
        self.assertEqual(
            [(node.code, node.position_code, node.mode) for node in nodes],
            [
                ("handler", "supply.business_handler", "shared_position"),
                ("company_leader", "supply.company_leader", "designated_user"),
                ("legal_counsel", "external.legal_counsel", "designated_user"),
                ("supply_risk_review", "investment.duty.supply_risk_review", "shared_position"),
                ("supply_governance_leader", "governance.supply_leader", "designated_user"),
            ],
        )
        self.assertTrue(nodes[0].auto_complete_on_submit)
        self.assertFalse(nodes[0].allow_reject)
        self.assertTrue(all(node.allow_reject for node in nodes[1:]))

    def test_payment_workflow_matches_confirmed_chain(self):
        nodes = WORKFLOW_CATALOG["supply.payment.v2"]
        self.assertEqual(
            [node.position_code for node in nodes],
            [
                "supply.business_handler",
                "supply.business_reviewer",
                "supply.finance_handler",
                "supply.company_leader",
                "investment.duty.supply_risk_review",
                "investment.duty.supply_finance_review",
                "governance.supply_leader",
            ],
        )
        self.assertEqual(
            [node.mode for node in nodes],
            [
                "shared_position",
                "shared_position",
                "shared_position",
                "designated_user",
                "shared_position",
                "shared_position",
                "designated_user",
            ],
        )

    def test_business_workflow_matches_confirmed_chain(self):
        nodes = WORKFLOW_CATALOG["supply.business.v2"]
        self.assertEqual(
            [node.code for node in nodes],
            [
                "handler",
                "reviewer",
                "company_leader",
                "supply_risk_review",
                "supply_governance_leader",
            ],
        )


class WorkflowPublicationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.publisher = User(
            username="publisher",
            full_name="Publisher",
            hashed_password="test",
            is_active=True,
        )
        self.db.add(self.publisher)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_assignment(
        self,
        username,
        position_code,
        valid_from=date(2026, 1, 1),
        valid_until=None,
        assignment_status=AssignmentStatus.ACTIVE,
        user_active=True,
        organization_active=True,
        position_active=True,
    ):
        user = self.db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username,
                full_name=username,
                hashed_password="test",
                is_active=user_active,
            )
            self.db.add(user)
            self.db.flush()
        organization = self.db.scalar(
            select(Organization).where(Organization.code == f"org.{position_code}")
        )
        if organization is None:
            organization = Organization(
                code=f"org.{position_code}",
                name=position_code,
                organization_type="department",
                is_active=organization_active,
            )
            self.db.add(organization)
            self.db.flush()
        position = self.db.scalar(select(Position).where(Position.code == position_code))
        if position is None:
            position = Position(
                code=position_code,
                name=position_code,
                category=PositionCategory.BUSINESS,
                is_active=position_active,
            )
            self.db.add(position)
            self.db.flush()
        assignment = UserAssignment(
            user_id=user.id,
            organization_id=organization.id,
            position_id=position.id,
            valid_from=valid_from,
            valid_until=valid_until,
            status=assignment_status,
        )
        self.db.add(assignment)
        self.db.commit()
        return assignment

    def version(self, code="supply.contract.v2"):
        return self.db.scalar(
            select(WorkflowVersion)
            .join(WorkflowVersion.definition)
            .where(WorkflowDefinition.code == code)
        )

    def assert_parent_pending_unflushed(self, pending):
        self.assertIn(pending, self.db.new)
        self.assertIsNone(pending.id)
        with self.db.no_autoflush:
            self.assertIsNone(
                self.db.scalar(select(User).where(User.username == pending.username))
            )

    def test_seed_publishes_exact_three_versions_and_is_idempotent(self):
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        counts = (
            self.db.query(WorkflowDefinition).count(),
            self.db.query(WorkflowVersion).count(),
            self.db.query(WorkflowNode).count(),
        )
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        self.assertEqual(counts, (3, 3, 17))
        self.assertEqual(
            (self.db.query(WorkflowDefinition).count(), self.db.query(WorkflowVersion).count(), self.db.query(WorkflowNode).count()),
            counts,
        )
        self.assertTrue(all(item.status == WorkflowVersionStatus.PUBLISHED for item in self.db.query(WorkflowVersion)))
        self.assertTrue(all(item.active_version_id is not None for item in self.db.query(WorkflowDefinition)))

    def test_catalog_drift_raises_without_mutation(self):
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        node = self.version().nodes[1]
        node.name = "drifted"
        self.db.commit()

        with self.assertRaises(WorkflowValidationError) as raised:
            seed_workflow_definitions(self.db, self.publisher.id)

        self.assertEqual(raised.exception.code, "workflow_catalog_drift")
        self.assertEqual(self.db.get(WorkflowNode, node.id).name, "drifted")
        self.assertEqual(self.db.query(WorkflowVersion).count(), 3)

    def test_published_version_is_immutable(self):
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        with self.assertRaises(WorkflowValidationError) as raised:
            ensure_workflow_version_mutable(self.version())
        self.assertEqual(raised.exception.code, "workflow_version_immutable")

    def test_conflict_validation_uses_inclusive_dates_and_designated_nodes(self):
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        left = self.add_assignment(
            "conflicted",
            "supply.company_leader",
            valid_until=date(2026, 6, 30),
        )
        right = self.add_assignment(
            "conflicted",
            "external.legal_counsel",
            valid_from=date(2026, 6, 30),
        )

        issues = validate_workflow_version(self.db, self.version())

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "workflow_assignment_conflict")
        self.assertEqual(issues[0].user_id, left.user_id)
        self.assertEqual(issues[0].node_codes, ("company_leader", "legal_counsel"))
        self.assertNotEqual(left.position_id, right.position_id)

    def test_validation_ignores_nonoverlap_inactive_entities_and_same_position(self):
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        self.add_assignment("nonoverlap", "supply.business_handler", valid_until=date(2026, 6, 29))
        self.add_assignment("nonoverlap", "supply.company_leader", valid_from=date(2026, 6, 30))
        self.add_assignment("inactive-user", "supply.business_handler", user_active=False)
        self.add_assignment("inactive-user", "supply.company_leader")
        inactive_organization = self.add_assignment("inactive-org", "supply.business_handler")
        self.add_assignment("inactive-org", "supply.company_leader")
        inactive_organization.organization.is_active = False
        inactive_position = self.add_assignment("inactive-position", "supply.business_handler")
        self.add_assignment("inactive-position", "supply.company_leader")
        inactive_position.position.is_active = False
        self.add_assignment("inactive-assignment", "supply.business_handler", assignment_status=AssignmentStatus.INACTIVE)
        self.add_assignment("inactive-assignment", "supply.company_leader")
        self.db.commit()

        self.assertEqual(validate_workflow_version(self.db, self.version()), [])

    def test_publication_conflict_is_atomic_and_leaves_no_catalog_rows(self):
        self.add_assignment("conflicted", "supply.business_handler")
        self.add_assignment("conflicted", "supply.company_leader")

        with self.assertRaises(WorkflowValidationError) as raised:
            seed_workflow_definitions(self.db, self.publisher.id)

        self.assertEqual(raised.exception.code, "workflow_validation_failed")
        self.assertEqual(self.db.query(WorkflowDefinition).count(), 0)
        self.assertEqual(self.db.query(WorkflowVersion).count(), 0)
        self.assertEqual(self.db.query(WorkflowNode).count(), 0)

    def test_success_preserves_pending_caller_object_and_leaves_commit_to_caller(self):
        publisher_id = self.publisher.id
        pending = User(
            username="pending-success",
            full_name="Pending Success",
            hashed_password="test",
        )
        self.db.add(pending)

        seed_workflow_definitions(self.db, publisher_id)

        self.assertTrue(self.db.in_transaction())
        self.assert_parent_pending_unflushed(pending)
        with self.db.no_autoflush:
            self.assertEqual(self.db.query(WorkflowDefinition).count(), 3)
        self.db.commit()
        self.assertIsNotNone(self.db.scalar(select(User).where(User.username == "pending-success")))
        self.assertEqual(self.db.query(WorkflowDefinition).count(), 3)

    def test_drift_preserves_pending_caller_object_and_outer_transaction(self):
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        node = self.version().nodes[1]
        node.name = "drifted"
        self.db.commit()
        publisher_id = self.publisher.id
        pending = User(
            username="pending-drift",
            full_name="Pending Drift",
            hashed_password="test",
        )
        self.db.add(pending)

        with self.assertRaises(WorkflowValidationError):
            seed_workflow_definitions(self.db, publisher_id)

        self.assertTrue(self.db.in_transaction())
        self.assert_parent_pending_unflushed(pending)
        self.db.commit()
        self.assertIsNotNone(self.db.scalar(select(User).where(User.username == "pending-drift")))

    def test_validation_error_preserves_pending_caller_object(self):
        self.add_assignment("conflicted", "supply.business_handler")
        self.add_assignment("conflicted", "supply.company_leader")
        publisher_id = self.publisher.id
        pending = User(
            username="pending-validation",
            full_name="Pending Validation",
            hashed_password="test",
        )
        self.db.add(pending)

        with self.assertRaises(WorkflowValidationError):
            seed_workflow_definitions(self.db, publisher_id)

        self.assert_parent_pending_unflushed(pending)
        self.db.commit()
        self.assertIsNotNone(self.db.scalar(select(User).where(User.username == "pending-validation")))
        self.assertEqual(self.db.query(WorkflowDefinition).count(), 0)

    def test_recognized_unique_race_reloads_exact_catalog(self):
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        publisher_id = self.publisher.id
        pending = User(
            username="pending-race",
            full_name="Pending Race",
            hashed_password="test",
        )
        self.db.add(pending)
        with patch(
            "app.services.workflow_engine._seed_workflow_definitions",
            side_effect=IntegrityError(
                "INSERT INTO wf_definition",
                {},
                Exception("UNIQUE constraint failed: wf_definition.code"),
            ),
        ):
            seed_workflow_definitions(self.db, publisher_id)

        self.assert_parent_pending_unflushed(pending)
        self.assertEqual(self.db.query(WorkflowDefinition).count(), 3)

    def test_unrelated_integrity_error_is_not_swallowed(self):
        with patch(
            "app.services.workflow_engine._seed_workflow_definitions",
            side_effect=IntegrityError(
                "INSERT INTO sys_user",
                {},
                Exception("NOT NULL constraint failed: sys_user.username"),
            ),
        ):
            with self.assertRaises(IntegrityError):
                seed_workflow_definitions(self.db, self.publisher.id)

    def test_recognized_unique_race_reload_rejects_drift(self):
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        publisher_id = self.publisher.id
        node = self.version().nodes[1]
        node.name = "concurrent drift"
        self.db.commit()
        pending = User(
            username="pending-race-drift",
            full_name="Pending Race Drift",
            hashed_password="test",
        )
        self.db.add(pending)

        with patch(
            "app.services.workflow_engine._seed_workflow_definitions",
            side_effect=IntegrityError(
                "INSERT INTO wf_definition",
                {},
                Exception("UNIQUE constraint failed: wf_definition.code"),
            ),
        ):
            with self.assertRaises(WorkflowValidationError) as raised:
                seed_workflow_definitions(self.db, publisher_id)

        self.assertEqual(raised.exception.code, "workflow_catalog_drift")
        self.assert_parent_pending_unflushed(pending)

    def test_catalog_changes_roll_back_with_caller_transaction(self):
        seed_workflow_definitions(self.db, self.publisher.id)
        with self.db.no_autoflush:
            self.assertEqual(self.db.query(WorkflowDefinition).count(), 3)

        self.db.rollback()

        self.assertEqual(self.db.query(WorkflowDefinition).count(), 0)


if __name__ == "__main__":
    unittest.main()
