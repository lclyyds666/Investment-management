import unittest
import tempfile
import threading
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.db.init_db  # noqa: F401
from app.core.enums import (
    AssignmentStatus,
    ContractStatus,
    ContractType,
    OrganizationType,
    PositionCategory,
    WorkflowAction,
    WorkflowAssigneeMode,
    WorkflowInstanceStatus,
    WorkflowTargetType,
    WorkflowTaskStatus,
    WorkflowVersionStatus,
)
from app.db.base import Base
from app.models.approval import Approval
from app.models.approval_form import ApprovalForm, ApprovalFormAction
from app.models.contract import Contract
from app.models.organization import ExternalAssignment, Organization, Position, UserAssignment
from app.models.user import User
from app.models.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowNode,
    WorkflowTask,
    WorkflowTaskAction,
    WorkflowVersion,
)
from app.services.workflow_catalog import WORKFLOW_CATALOG
from app.services.workflow_engine import (
    WorkflowTaskConflict,
    WorkflowValidationError,
    _load_task_conflict_after_rollback,
    actionable_active_task_counts,
    complete_task,
    eligible_designated_users,
    ensure_workflow_version_mutable,
    my_active_tasks,
    refresh_invalid_designated_tasks,
    seed_workflow_definitions,
    start_workflow,
    materialize_legacy_workflow,
    task_is_actionable_by,
    validate_workflow_version,
)
from scripts.migrate_active_workflows import (
    ReportFinalizeError,
    _apply_failure_outcome,
    migrate_active_workflows,
    save_active_workflow_migration_report,
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


class WorkflowStartTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.users = {}
        self.publisher = self.add_user("publisher", "Publisher")
        self.handler = self.add_assignment("handler", "Handler", "supply.business_handler").user
        self.leader = self.add_assignment("leader", "Amy Leader", "supply.company_leader").user
        self.legal = self.add_assignment(
            "legal", "Bob Legal", "external.legal_counsel", external_scope=True
        ).user
        self.governance = self.add_assignment(
            "governance", "Cara Governance", "governance.supply_leader"
        ).user
        self.db.commit()
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        self.contract = Contract(
            contract_no="TASK3-001",
            title="Task 3 Contract",
            created_by=self.handler.id,
        )
        self.db.add(self.contract)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_user(self, username, full_name, active=True):
        user = User(
            username=username,
            full_name=full_name,
            hashed_password="test",
            is_active=active,
        )
        self.db.add(user)
        self.db.flush()
        self.users[username] = user
        return user

    def add_assignment(
        self,
        username,
        full_name,
        position_code,
        *,
        valid_from=date(2026, 1, 1),
        valid_until=None,
        assignment_status=AssignmentStatus.ACTIVE,
        user_active=True,
        organization_active=True,
        position_active=True,
        external_scope=False,
    ):
        user = self.users.get(username) or self.add_user(username, full_name, user_active)
        organization = self.db.scalar(
            select(Organization).where(Organization.code == f"org.{position_code}")
        )
        if organization is None:
            organization = Organization(
                code=f"org.{position_code}",
                name=f"Org {position_code}",
                organization_type=(
                    OrganizationType.EXTERNAL
                    if position_code.startswith("external.")
                    else OrganizationType.DEPARTMENT
                ),
                is_active=organization_active,
            )
            self.db.add(organization)
            self.db.flush()
        position = self.db.scalar(select(Position).where(Position.code == position_code))
        if position is None:
            position = Position(
                code=position_code,
                name=f"Position {position_code}",
                category=(
                    PositionCategory.EXTERNAL
                    if position_code.startswith("external.")
                    else PositionCategory.BUSINESS
                ),
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
        self.db.flush()
        if position_code == "external.legal_counsel":
            assignment.external_detail = ExternalAssignment(
                provider_name="Legal Provider",
                service_scopes=["contract_legal_review"] if external_scope else ["other"],
            )
        return assignment

    def designated_users(self):
        return {
            "company_leader": self.leader.id,
            "legal_counsel": self.legal.id,
            "supply_governance_leader": self.governance.id,
        }

    def test_candidate_list_filters_scope_dates_and_active_entities_then_sorts_and_dedupes(self):
        self.add_assignment("leader", "Amy Leader", "supply.company_leader")
        self.add_assignment(
            "later",
            "Zed Later",
            "supply.company_leader",
            valid_from=date(2026, 2, 1),
            valid_until=date(2026, 12, 31),
        )
        self.add_assignment(
            "expired", "Expired", "supply.company_leader", valid_until=date(2026, 8, 11)
        )
        self.add_assignment(
            "inactive", "Inactive", "supply.company_leader", user_active=False
        )
        wrong_scope = self.add_assignment(
            "wrong-scope", "Wrong Scope", "external.legal_counsel"
        )
        self.db.commit()

        candidates = eligible_designated_users(
            self.db, "supply.contract.v2", "company_leader", date(2026, 8, 12)
        )
        legal_candidates = eligible_designated_users(
            self.db, "supply.contract.v2", "legal_counsel", date(2026, 8, 12)
        )

        self.assertEqual([item.user_id for item in candidates], [self.leader.id, self.users["later"].id])
        self.assertEqual(candidates[0].assignment_id, min(item.id for item in self.leader.assignments))
        self.assertEqual(candidates[0].valid_from, date(2026, 1, 1))
        self.assertIsNone(candidates[0].valid_until)
        self.assertEqual(candidates[1].valid_from, date(2026, 2, 1))
        self.assertEqual(candidates[1].valid_until, date(2026, 12, 31))
        without_leader = eligible_designated_users(
            self.db,
            "supply.contract.v2",
            "company_leader",
            date(2026, 8, 12),
            exclude_user_id=self.leader.id,
        )
        self.assertEqual([item.user_id for item in without_leader], [self.users["later"].id])
        self.assertEqual([item.user_id for item in legal_candidates], [self.legal.id])
        self.assertNotEqual(wrong_scope.user_id, self.legal.id)

    def test_start_materializes_all_tasks_and_submit_snapshot(self):
        instance = start_workflow(
            self.db,
            WorkflowTargetType.CONTRACT,
            self.contract.id,
            self.handler,
            self.designated_users(),
        )

        self.assertTrue(self.db.in_transaction())
        self.assertEqual(instance.current_sequence, 1)
        tasks = list(self.db.scalars(
            select(WorkflowTask).where(WorkflowTask.instance_id == instance.id).order_by(WorkflowTask.sequence)
        ))
        self.assertEqual(len(tasks), 5)
        self.assertEqual(
            [task.status for task in tasks],
            [
                WorkflowTaskStatus.APPROVED,
                WorkflowTaskStatus.ACTIVE,
                WorkflowTaskStatus.PENDING,
                WorkflowTaskStatus.PENDING,
                WorkflowTaskStatus.PENDING,
            ],
        )
        self.assertIsNone(tasks[0].designated_user_id)
        self.assertEqual(tasks[1].designated_user_id, self.leader.id)
        self.assertIsNotNone(tasks[1].designated_assignment_id)
        self.assertTrue(all(
            task.designated_user_id is None
            for task in tasks
            if task.assignee_mode == WorkflowAssigneeMode.SHARED_POSITION
        ))
        action = self.db.scalar(select(WorkflowTaskAction))
        self.assertEqual(action.action, WorkflowAction.SUBMIT)
        self.assertEqual(action.actor_id, self.handler.id)
        self.assertEqual(action.actor_name, self.handler.full_name)
        self.assertEqual(action.position_code, "supply.business_handler")
        self.assertEqual(action.signature_snapshot, self.handler.signature)
        projection = self.db.scalar(
            select(Approval).where(Approval.workflow_task_action_id == action.id)
        )
        self.assertEqual(projection.approver_role, "supply.business_handler")
        self.assertEqual(projection.position_code, action.position_code)
        self.assertEqual(projection.position_name, action.position_name)
        self.assertEqual(projection.organization_code, action.organization_code)
        self.assertEqual(projection.action.value, "approve")
        self.db.refresh(self.contract)
        self.assertEqual(self.contract.status, ContractStatus.PENDING)
        self.assertEqual(self.contract.current_step, 1)
        self.assertEqual(self.contract.workflow_instance_id, instance.id)

    def test_enabled_superuser_can_start_own_draft_with_governance_snapshot(self):
        admin = self.add_user("admin-submitter", "Admin Submitter")
        admin.is_superuser = True
        admin.signature = "admin-signature"
        contract = Contract(
            contract_no="TASK3-ADMIN",
            title="Admin Contract",
            created_by=admin.id,
        )
        self.db.add(contract)
        self.db.commit()

        instance = start_workflow(
            self.db,
            WorkflowTargetType.CONTRACT,
            contract.id,
            admin,
            self.designated_users(),
        )

        submit_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.sequence == 0,
        ))
        action = self.db.scalar(select(WorkflowTaskAction).where(
            WorkflowTaskAction.task_id == submit_task.id,
        ))
        first_approval_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.sequence == 1,
        ))
        self.assertEqual(action.actor_id, admin.id)
        self.assertEqual(action.actor_name, admin.full_name)
        self.assertEqual(action.organization_code, "system.governance")
        self.assertEqual(action.organization_name, "系统治理")
        self.assertEqual(action.position_code, "system.superuser")
        self.assertEqual(action.position_name, "超级管理员")
        self.assertEqual(action.signature_snapshot, admin.signature)
        self.assertEqual(first_approval_task.status, WorkflowTaskStatus.ACTIVE)
        self.assertIsNone(self.db.scalar(select(UserAssignment).where(
            UserAssignment.user_id == admin.id,
        )))

    def test_disabled_superuser_cannot_start_own_draft_without_assignment(self):
        admin = self.add_user("disabled-admin-submitter", "Disabled Admin")
        admin.is_superuser = True
        admin.is_active = False
        contract = Contract(
            contract_no="TASK3-DISABLED-ADMIN",
            title="Disabled Admin Contract",
            created_by=admin.id,
        )
        self.db.add(contract)
        self.db.commit()

        with self.assertRaises(WorkflowValidationError) as raised:
            start_workflow(
                self.db,
                WorkflowTargetType.CONTRACT,
                contract.id,
                admin,
                self.designated_users(),
            )

        self.assertEqual(raised.exception.code, "ineligible_workflow_submitter")
        self.assertIsNone(self.db.scalar(select(UserAssignment).where(
            UserAssignment.user_id == admin.id,
        )))
        self.db.refresh(contract)
        self.assertEqual(contract.status, ContractStatus.DRAFT)
        self.assertIsNone(contract.workflow_instance_id)
        self.assertEqual(self.db.query(WorkflowInstance).count(), 0)
        self.assertEqual(self.db.query(WorkflowTaskAction).count(), 0)

    def test_start_supports_payment_and_business_targets(self):
        payment = ApprovalForm(
            form_type=ContractType.PAYMENT,
            created_by=self.handler.id,
        )
        business = ApprovalForm(
            form_type=ContractType.BUSINESS,
            created_by=self.handler.id,
        )
        self.db.add_all([payment, business])
        self.db.commit()

        payment_instance = start_workflow(
            self.db,
            WorkflowTargetType.PAYMENT_APPROVAL,
            payment.id,
            self.handler,
            {
                "company_leader": self.leader.id,
                "supply_governance_leader": self.governance.id,
            },
        )
        business_instance = start_workflow(
            self.db,
            WorkflowTargetType.BUSINESS_APPROVAL,
            business.id,
            self.handler,
            {
                "company_leader": self.leader.id,
                "supply_governance_leader": self.governance.id,
            },
        )

        self.assertEqual(self.db.query(WorkflowTask).filter_by(instance_id=payment_instance.id).count(), 7)
        self.assertEqual(self.db.query(WorkflowTask).filter_by(instance_id=business_instance.id).count(), 5)

    def test_start_rejects_missing_extra_ineligible_and_duplicate_people(self):
        cases = [
            ({"company_leader": self.leader.id}, "missing_designated_user"),
            ({**self.designated_users(), "unknown": self.leader.id}, "unknown_designated_node"),
            ({**self.designated_users(), "legal_counsel": self.publisher.id}, "ineligible_designated_user"),
            ({**self.designated_users(), "legal_counsel": self.leader.id}, "duplicate_workflow_actor"),
            ({**self.designated_users(), "company_leader": self.handler.id}, "duplicate_workflow_actor"),
        ]
        for designated_users, code in cases:
            with self.subTest(code=code, designated_users=designated_users):
                with self.assertRaises(WorkflowValidationError) as raised:
                    start_workflow(
                        self.db,
                        WorkflowTargetType.CONTRACT,
                        self.contract.id,
                        self.handler,
                        designated_users,
                    )
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(self.db.query(WorkflowInstance).count(), 0)
                self.assertEqual(self.db.query(WorkflowTask).count(), 0)
                self.assertEqual(self.db.query(WorkflowTaskAction).count(), 0)

    def test_start_rejects_wrong_owner_and_duplicate_target_atomically(self):
        outsider = self.add_assignment(
            "outsider", "Outsider", "supply.business_handler"
        ).user
        self.db.commit()
        with self.assertRaises(WorkflowValidationError) as raised:
            start_workflow(
                self.db,
                WorkflowTargetType.CONTRACT,
                self.contract.id,
                outsider,
                self.designated_users(),
            )
        self.assertEqual(raised.exception.code, "workflow_submitter_not_owner")

        start_workflow(
            self.db,
            WorkflowTargetType.CONTRACT,
            self.contract.id,
            self.handler,
            self.designated_users(),
        )
        with self.assertRaises(WorkflowValidationError) as raised:
            start_workflow(
                self.db,
                WorkflowTargetType.CONTRACT,
                self.contract.id,
                self.handler,
                self.designated_users(),
            )
        self.assertEqual(raised.exception.code, "workflow_already_started")
        self.assertEqual(self.db.query(WorkflowInstance).count(), 1)

    def test_concurrent_unique_conflict_preserves_parent_transaction_and_pending_objects(self):
        target_id = self.contract.id
        handler_id = self.handler.id
        designated_users = self.designated_users()
        definition = self.db.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.code == "supply.contract.v2"
            )
        )
        definition_id = definition.id
        version_id = definition.active_version_id
        existing = WorkflowInstance(
            definition_id=definition_id,
            version_id=version_id,
            target_type=WorkflowTargetType.CONTRACT,
            target_id=target_id,
            status=WorkflowInstanceStatus.ACTIVE,
            current_sequence=1,
            submitted_by=handler_id,
            submitted_at=datetime(2026, 8, 12, 9, 0),
        )
        self.db.add(existing)
        self.db.commit()
        pending = User(
            username="pending-concurrent-start",
            full_name="Pending Concurrent Start",
            hashed_password="test",
        )
        self.db.add(pending)

        def insert_concurrent_duplicate(workflow_db, *_args):
            workflow_db.add(WorkflowInstance(
                definition_id=definition_id,
                version_id=version_id,
                target_type=WorkflowTargetType.CONTRACT,
                target_id=target_id,
                status=WorkflowInstanceStatus.ACTIVE,
                current_sequence=1,
                submitted_by=handler_id,
                submitted_at=datetime(2026, 8, 12, 9, 1),
            ))
            workflow_db.flush()

        with patch(
            "app.services.workflow_engine._start_workflow",
            side_effect=insert_concurrent_duplicate,
        ):
            with self.assertRaises(WorkflowValidationError) as raised:
                start_workflow(
                    self.db,
                    WorkflowTargetType.CONTRACT,
                    target_id,
                    self.handler,
                    designated_users,
                )

        self.assertEqual(raised.exception.code, "workflow_already_started")
        self.assertEqual(
            raised.exception.details,
            {"target_type": "contract", "target_id": target_id},
        )
        self.assertTrue(self.db.in_transaction())
        self.assertIn(pending, self.db.new)
        self.assertIsNone(pending.id)
        with self.db.no_autoflush:
            self.assertEqual(self.db.query(WorkflowInstance).count(), 1)
        self.db.commit()
        self.assertEqual(self.db.query(WorkflowInstance).count(), 1)
        self.assertIsNotNone(
            self.db.scalar(
                select(User).where(User.username == "pending-concurrent-start")
            )
        )

    def test_failed_start_preserves_parent_pending_and_success_rolls_back_with_caller(self):
        valid_designated_users = self.designated_users()
        target_id = self.contract.id
        pending = User(username="pending-task3", full_name="Pending", hashed_password="test")
        self.db.add(pending)
        invalid = dict(valid_designated_users)
        invalid.pop("legal_counsel")

        with self.assertRaises(WorkflowValidationError):
            start_workflow(
                self.db,
                WorkflowTargetType.CONTRACT,
                target_id,
                self.handler,
                invalid,
            )
        self.assertIn(pending, self.db.new)
        self.assertIsNone(pending.id)

        instance = start_workflow(
            self.db,
            WorkflowTargetType.CONTRACT,
            target_id,
            self.handler,
            valid_designated_users,
        )
        self.assertIsNotNone(instance.id)
        self.assertIn(pending, self.db.new)
        self.assertIsNone(pending.id)
        self.db.expunge(pending)
        self.db.rollback()
        self.assertEqual(self.db.query(WorkflowInstance).count(), 0)
        self.assertIsNone(self.db.get(Contract, target_id).workflow_instance_id)


class ActiveWorkflowMigrationTest(unittest.TestCase):
    add_user = WorkflowStartTest.add_user
    add_assignment = WorkflowStartTest.add_assignment

    def setUp(self):
        WorkflowStartTest.setUp(self)
        self.contract.status = ContractStatus.PENDING
        self.contract.current_step = 3
        self.db.add(Approval(
            contract_id=self.contract.id,
            approver_id=self.handler.id,
            step=0,
            approver_role="business_handler",
            action="approve",
            comment="legacy submit",
        ))
        self.db.commit()

    def tearDown(self):
        WorkflowStartTest.tearDown(self)

    def add_form(self, form_type, status, current_step):
        form = ApprovalForm(
            form_type=form_type,
            created_by=self.handler.id,
            status=status,
            current_step=current_step,
        )
        self.db.add(form)
        self.db.flush()
        return form

    def report_item(self, report, target_type, target_id):
        return next(
            item for item in report["items"]
            if item["target_type"] == target_type and item["target_id"] == target_id
        )

    def test_dry_run_classifies_all_legacy_states_without_writes(self):
        designated_current = self.add_form(ContractType.PAYMENT, ContractStatus.PENDING, 3)
        invalid = Contract(
            contract_no="TASK9-INVALID",
            title="Invalid legacy state",
            created_by=self.handler.id,
            status=ContractStatus.PENDING,
            current_step=99,
        )
        historical_approved = self.add_form(
            ContractType.BUSINESS, ContractStatus.APPROVED, 4
        )
        historical_rejected = Contract(
            contract_no="TASK9-REJECTED",
            title="Historical rejected",
            created_by=self.handler.id,
            status=ContractStatus.REJECTED,
            current_step=2,
        )
        self.db.add_all([invalid, historical_rejected])
        self.db.commit()
        before = {
            "instances": self.db.query(WorkflowInstance).count(),
            "tasks": self.db.query(WorkflowTask).count(),
            "actions": self.db.query(WorkflowTaskAction).count(),
            "approvals": self.db.query(Approval).count(),
        }

        report = migrate_active_workflows(
            self.db, apply=False, as_of=date(2026, 8, 13)
        )

        shared = self.report_item(report, "contract", self.contract.id)
        self.assertEqual(shared["current_step"], 3)
        self.assertEqual(shared["expected_role"], "risk_auditor")
        self.assertEqual(shared["classification"], "mappable_shared")
        self.assertEqual(shared["admin_action"], "run apply migration")
        self.assertEqual(
            self.report_item(report, "payment_approval", designated_current.id)["classification"],
            "needs_designation",
        )
        self.assertEqual(
            self.report_item(report, "contract", invalid.id)["classification"],
            "invalid_state",
        )
        self.assertEqual(
            self.report_item(report, "business_approval", historical_approved.id)["classification"],
            "historical_only",
        )
        self.assertEqual(
            self.report_item(report, "contract", historical_rejected.id)["classification"],
            "historical_only",
        )
        self.assertEqual(before, {
            "instances": self.db.query(WorkflowInstance).count(),
            "tasks": self.db.query(WorkflowTask).count(),
            "actions": self.db.query(WorkflowTaskAction).count(),
            "approvals": self.db.query(Approval).count(),
        })
        self.assertIsNone(self.contract.workflow_instance_id)

    def test_apply_materializes_tasks_without_submit_or_approval_audit_and_is_idempotent(self):
        original_approval_count = self.db.query(Approval).count()
        handler_assignment = next(
            item for item in self.handler.assignments
            if item.position.code == "supply.business_handler"
        )
        handler_assignment.status = AssignmentStatus.INACTIVE
        self.db.commit()

        report = migrate_active_workflows(
            self.db,
            apply=True,
            as_of=date(2026, 8, 13),
            migrated_at=datetime(2026, 8, 13, 9, 0),
        )

        self.assertEqual(report["migrated"], 1)
        self.db.refresh(self.contract)
        instance = self.db.get(WorkflowInstance, self.contract.workflow_instance_id)
        self.assertEqual(instance.current_sequence, 3)
        self.assertEqual(instance.submitted_by, self.handler.id)
        tasks = list(self.db.scalars(
            select(WorkflowTask)
            .where(WorkflowTask.instance_id == instance.id)
            .order_by(WorkflowTask.sequence)
        ))
        self.assertEqual(
            [task.status for task in tasks],
            [
                WorkflowTaskStatus.APPROVED,
                WorkflowTaskStatus.APPROVED,
                WorkflowTaskStatus.APPROVED,
                WorkflowTaskStatus.ACTIVE,
                WorkflowTaskStatus.PENDING,
            ],
        )
        self.assertEqual(tasks[4].designated_user_id, self.governance.id)
        self.assertIsNotNone(tasks[4].designated_assignment_id)
        self.assertEqual(self.db.query(WorkflowTaskAction).count(), 0)
        self.assertEqual(self.db.query(Approval).count(), original_approval_count)

        second = migrate_active_workflows(
            self.db, apply=True, as_of=date(2026, 8, 13)
        )
        self.assertEqual(second["migrated"], 0)
        self.assertEqual(self.db.query(WorkflowInstance).count(), 1)
        self.assertEqual(self.db.query(WorkflowTask).count(), 5)

    def test_apply_never_guesses_zero_or_multiple_future_designated_users(self):
        self.governance.is_active = False
        self.db.commit()
        zero_report = migrate_active_workflows(
            self.db, apply=True, as_of=date(2026, 8, 13)
        )
        zero_item = self.report_item(zero_report, "contract", self.contract.id)
        self.assertEqual(zero_item["classification"], "needs_designation")
        self.assertIn("supply_governance_leader", zero_item["admin_action"])
        self.assertEqual(self.db.query(WorkflowInstance).count(), 0)

        self.governance.is_active = True
        self.add_assignment(
            "governance-2", "Other Governance", "governance.supply_leader"
        )
        self.db.commit()
        multiple_report = migrate_active_workflows(
            self.db, apply=True, as_of=date(2026, 8, 13)
        )
        multiple_item = self.report_item(multiple_report, "contract", self.contract.id)
        self.assertEqual(multiple_item["classification"], "needs_designation")
        self.assertEqual(self.db.query(WorkflowInstance).count(), 0)

    def test_apply_materializes_approval_form_without_legacy_action(self):
        self.contract.status = ContractStatus.APPROVED
        payment = self.add_form(
            ContractType.PAYMENT, ContractStatus.PENDING, 1
        )
        self.db.commit()

        report = migrate_active_workflows(
            self.db,
            apply=True,
            as_of=date(2026, 8, 13),
            migrated_at=datetime(2026, 8, 13, 9, 0),
        )

        self.assertEqual(report["migrated"], 1)
        self.db.refresh(payment)
        instance = self.db.get(WorkflowInstance, payment.workflow_instance_id)
        self.assertEqual(instance.target_type, WorkflowTargetType.PAYMENT_APPROVAL)
        self.assertEqual(instance.current_sequence, 1)
        self.assertEqual(self.db.query(WorkflowTask).filter_by(
            instance_id=instance.id
        ).count(), 7)
        self.assertEqual(self.db.query(WorkflowTaskAction).count(), 0)
        self.assertEqual(self.db.query(ApprovalFormAction).count(), 0)

    def test_apply_participates_in_caller_transaction(self):
        pending = User(
            username="pending-task9",
            full_name="Pending Task 9",
            hashed_password="test",
        )
        self.db.add(pending)
        migrate_active_workflows(
            self.db, apply=True, as_of=date(2026, 8, 13)
        )
        self.assertIn(pending, self.db.new)
        self.assertIsNone(pending.id)
        with self.db.no_autoflush:
            self.assertEqual(self.db.query(WorkflowInstance).count(), 1)

        self.db.rollback()

        self.assertEqual(self.db.query(WorkflowInstance).count(), 0)
        self.assertIsNone(self.db.get(Contract, self.contract.id).workflow_instance_id)

    def test_unlinked_existing_instance_is_invalid_state_not_a_second_instance(self):
        definition = self.db.scalar(select(WorkflowDefinition).where(
            WorkflowDefinition.code == "supply.contract.v2"
        ))
        self.db.add(WorkflowInstance(
            definition_id=definition.id,
            version_id=definition.active_version_id,
            target_type=WorkflowTargetType.CONTRACT,
            target_id=self.contract.id,
            status=WorkflowInstanceStatus.ACTIVE,
            current_sequence=3,
            submitted_by=self.handler.id,
            submitted_at=datetime(2026, 8, 12, 9, 0),
        ))
        self.db.commit()

        report = migrate_active_workflows(
            self.db, apply=True, as_of=date(2026, 8, 13)
        )

        item = self.report_item(report, "contract", self.contract.id)
        self.assertEqual(item["classification"], "invalid_state")
        self.assertIn("workflow instance", item["admin_action"])
        self.assertEqual(self.db.query(WorkflowInstance).count(), 1)

    def test_apply_rejects_persisted_catalog_drift_without_materializing(self):
        node = self.db.scalar(select(WorkflowNode).where(
            WorkflowNode.version_id == self.db.scalar(
                select(WorkflowDefinition.active_version_id).where(
                    WorkflowDefinition.code == "supply.contract.v2"
                )
            ),
            WorkflowNode.sequence == 3,
        ))
        node.position_code = "wrong.risk.position"
        self.db.commit()

        report = migrate_active_workflows(
            self.db, apply=True, as_of=date(2026, 8, 13)
        )

        item = self.report_item(report, "contract", self.contract.id)
        self.assertEqual(item["classification"], "mappable_shared")
        self.assertEqual(item["outcome"], "invalid_state")
        self.assertIn("catalog drift", item["admin_action"])
        self.assertEqual(self.db.query(WorkflowInstance).count(), 0)

    def test_apply_revalidates_designations_on_explicit_as_of_date(self):
        governance_assignment = next(
            item for item in self.governance.assignments
            if item.position.code == "governance.supply_leader"
        )
        governance_assignment.valid_until = date(2026, 8, 13)
        self.db.commit()

        report = migrate_active_workflows(
            self.db,
            apply=True,
            as_of=date(2026, 8, 13),
            migrated_at=datetime(2026, 8, 14, 0, 1),
        )

        item = self.report_item(report, "contract", self.contract.id)
        self.assertEqual(item["outcome"], "migrated")
        self.assertIsNotNone(self.db.get(Contract, self.contract.id).workflow_instance_id)

    def test_unique_race_becomes_stable_invalid_outcome_and_batch_continues(self):
        second = Contract(
            contract_no="TASK9-RACE-SECOND",
            title="Race second target",
            created_by=self.handler.id,
            status=ContractStatus.PENDING,
            current_step=3,
        )
        self.db.add(second)
        self.db.commit()
        real_materialize = materialize_legacy_workflow
        raced = False

        def race_once(db, target_type, target_id, *args, **kwargs):
            nonlocal raced
            if not raced:
                raced = True
                definition = db.scalar(select(WorkflowDefinition).where(
                    WorkflowDefinition.code == "supply.contract.v2"
                ))
                db.add(WorkflowInstance(
                    definition_id=definition.id,
                    version_id=definition.active_version_id,
                    target_type=target_type,
                    target_id=target_id,
                    status=WorkflowInstanceStatus.ACTIVE,
                    current_sequence=3,
                    submitted_by=self.handler.id,
                    submitted_at=datetime(2026, 8, 13, 9, 0),
                ))
                db.flush()
                raise WorkflowValidationError(
                    "workflow_already_started",
                    "Concurrent workflow materialization won the race.",
                )
            return real_materialize(db, target_type, target_id, *args, **kwargs)

        with patch(
            "scripts.migrate_active_workflows.materialize_legacy_workflow",
            side_effect=race_once,
        ):
            report = migrate_active_workflows(
                self.db, apply=True, as_of=date(2026, 8, 13)
            )

        first_item = self.report_item(report, "contract", self.contract.id)
        second_item = self.report_item(report, "contract", second.id)
        self.assertEqual(first_item["outcome"], "invalid_state")
        self.assertEqual(second_item["outcome"], "migrated")
        self.assertEqual(report["outcome_counts"], {"invalid_state": 1, "migrated": 1})
        self.assertTrue(self.db.in_transaction())
        self.assertEqual(self.db.query(WorkflowInstance).count(), 2)

    def test_report_path_failure_prevents_database_migration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "missing" / "report.json"
            with self.assertRaises(OSError):
                save_active_workflow_migration_report(
                    self.db,
                    report_path,
                    apply=True,
                    as_of=date(2026, 8, 13),
                )

        self.assertEqual(self.db.query(WorkflowInstance).count(), 0)
        self.assertIsNone(self.db.get(Contract, self.contract.id).workflow_instance_id)

    def test_successful_cutover_commits_database_and_atomically_saves_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            report = save_active_workflow_migration_report(
                self.db,
                report_path,
                apply=True,
                as_of=date(2026, 8, 13),
            )

            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(saved, report)
            self.assertEqual(saved["outcome_counts"], {"migrated": 1})
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])
        self.db.rollback()
        self.assertEqual(self.db.query(WorkflowInstance).count(), 1)

    def test_post_commit_rename_failure_preserves_recoverable_temp_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            with patch(
                "scripts.migrate_active_workflows.os.replace",
                side_effect=OSError("rename failed"),
            ):
                with self.assertRaises(ReportFinalizeError) as raised:
                    save_active_workflow_migration_report(
                        self.db,
                        report_path,
                        apply=True,
                        as_of=date(2026, 8, 13),
                    )

            temp_reports = list(Path(temp_dir).glob("*.tmp"))
            self.assertEqual(len(temp_reports), 1)
            self.assertIn(str(temp_reports[0]), str(raised.exception))
            saved = json.loads(temp_reports[0].read_text(encoding="utf-8"))
            self.assertEqual(saved["outcome_counts"], {"migrated": 1})
        self.db.rollback()
        self.assertEqual(self.db.query(WorkflowInstance).count(), 1)

    def test_apply_rejects_stale_scanned_step_and_continues_batch(self):
        second = Contract(
            contract_no="TASK9-STALE-SECOND",
            title="Stale scan second target",
            created_by=self.handler.id,
            status=ContractStatus.PENDING,
            current_step=3,
        )
        self.db.add(second)
        self.db.commit()
        real_materialize = materialize_legacy_workflow
        changed = False

        def change_step_after_scan(db, target_type, target_id, *args, **kwargs):
            nonlocal changed
            if not changed:
                changed = True
                db.execute(
                    update(Contract)
                    .where(Contract.id == target_id)
                    .values(current_step=4)
                    .execution_options(synchronize_session=False)
                )
                db.commit()
            return real_materialize(db, target_type, target_id, *args, **kwargs)

        with patch(
            "scripts.migrate_active_workflows.materialize_legacy_workflow",
            side_effect=change_step_after_scan,
        ):
            report = migrate_active_workflows(
                self.db, apply=True, as_of=date(2026, 8, 13)
            )

        stale = self.report_item(report, "contract", self.contract.id)
        continued = self.report_item(report, "contract", second.id)
        self.assertEqual(stale["classification"], "mappable_shared")
        self.assertEqual(stale["outcome"], "invalid_state")
        self.assertIn("legacy_workflow_stale_current_step", stale["admin_action"])
        self.assertEqual(continued["outcome"], "migrated")
        self.assertIsNone(self.db.get(Contract, self.contract.id).workflow_instance_id)
        self.assertIsNotNone(self.db.get(Contract, second.id).workflow_instance_id)
        self.assertEqual(self.db.query(WorkflowInstance).count(), 1)

    def test_validation_code_mapping_limits_needs_designation(self):
        designation_codes = {
            "legacy_workflow_designations_incomplete",
            "legacy_workflow_designation_invalid",
            "missing_designated_user",
            "ineligible_designated_user",
            "duplicate_workflow_actor",
        }
        invalid_codes = {
            "workflow_target_not_found",
            "workflow_not_published",
            "workflow_catalog_drift",
            "legacy_workflow_current_step_not_shared",
            "legacy_workflow_stale_current_step",
            "workflow_submitter_not_owner",
            "unknown_designated_node",
        }
        for code in designation_codes | invalid_codes:
            with self.subTest(code=code):
                item = {"outcome": "not_applied", "admin_action": ""}
                _apply_failure_outcome(
                    self.db,
                    item,
                    WorkflowTargetType.CONTRACT,
                    self.contract.id,
                    WorkflowValidationError(code, code),
                )
                self.assertEqual(
                    item["outcome"],
                    "needs_designation" if code in designation_codes else "invalid_state",
                )


class WorkflowAuthorizationTest(unittest.TestCase):
    add_user = WorkflowStartTest.add_user
    add_assignment = WorkflowStartTest.add_assignment
    designated_users = WorkflowStartTest.designated_users

    def setUp(self):
        WorkflowStartTest.setUp(self)
        self.reviewer_a = self.add_assignment(
            "reviewer-a", "Reviewer A", "investment.duty.supply_risk_review"
        ).user
        self.reviewer_b = self.add_assignment(
            "reviewer-b", "Reviewer B", "investment.duty.supply_risk_review"
        ).user
        self.leader_b = self.add_assignment(
            "leader-b", "Leader B", "supply.company_leader"
        ).user
        self.admin = self.add_user("admin", "Admin")
        self.admin.is_superuser = True
        self.db.commit()
        self.instance = start_workflow(
            self.db,
            WorkflowTargetType.CONTRACT,
            self.contract.id,
            self.handler,
            self.designated_users(),
        )
        self.db.commit()
        self.designated_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == self.instance.id,
            WorkflowTask.sequence == 1,
        ))
        self.shared_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == self.instance.id,
            WorkflowTask.sequence == 3,
        ))
        self.db.commit()

    def test_any_active_shared_position_holder_can_act(self):
        self.shared_task.status = WorkflowTaskStatus.ACTIVE
        self.db.commit()
        self.assertTrue(task_is_actionable_by(self.db, self.shared_task, self.reviewer_a))
        self.assertTrue(task_is_actionable_by(self.db, self.shared_task, self.reviewer_b))

    def test_designated_task_only_allows_selected_user(self):
        self.assertTrue(task_is_actionable_by(self.db, self.designated_task, self.leader))
        self.assertFalse(task_is_actionable_by(self.db, self.designated_task, self.leader_b))
        self.assertEqual(self.designated_task.status, WorkflowTaskStatus.ACTIVE)

    def test_enabled_superuser_can_act_on_designated_and_shared_active_tasks(self):
        self.shared_task.status = WorkflowTaskStatus.ACTIVE
        self.db.commit()

        self.assertTrue(task_is_actionable_by(self.db, self.designated_task, self.admin))
        self.assertTrue(task_is_actionable_by(self.db, self.shared_task, self.admin))

        self.admin.is_active = False
        self.db.commit()
        self.assertFalse(task_is_actionable_by(self.db, self.designated_task, self.admin))

    def test_disabled_superuser_cannot_complete_or_resubmit_active_tasks(self):
        self.admin.is_active = False
        self.db.commit()
        self.assertIsNone(self.db.scalar(select(UserAssignment).where(
            UserAssignment.user_id == self.admin.id,
        )))

        for action in (WorkflowAction.APPROVE, WorkflowAction.RETURN):
            with self.subTest(action=action):
                with self.assertRaises(WorkflowValidationError) as raised:
                    complete_task(
                        self.db,
                        self.designated_task.id,
                        self.admin,
                        action,
                        "disabled admin action",
                    )
                self.assertEqual(raised.exception.code, "workflow_task_not_actionable")
                self.assertEqual(
                    self.db.get(WorkflowTask, self.designated_task.id).status,
                    WorkflowTaskStatus.ACTIVE,
                )
                self.assertEqual(
                    self.db.query(WorkflowTaskAction).filter_by(
                        task_id=self.designated_task.id
                    ).count(),
                    0,
                )

        complete_task(
            self.db,
            self.designated_task.id,
            self.leader,
            WorkflowAction.RETURN,
            "ordinary leader return",
        )
        handler_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == self.instance.id,
            WorkflowTask.sequence == 0,
        ))
        self.assertEqual(handler_task.status, WorkflowTaskStatus.ACTIVE)

        with self.assertRaises(WorkflowValidationError) as raised:
            complete_task(
                self.db,
                handler_task.id,
                self.admin,
                WorkflowAction.SUBMIT,
                "disabled admin resubmission",
            )

        self.assertEqual(raised.exception.code, "workflow_task_not_actionable")
        self.assertEqual(
            self.db.get(WorkflowTask, handler_task.id).status,
            WorkflowTaskStatus.ACTIVE,
        )
        self.assertEqual(
            self.db.query(WorkflowTaskAction).filter_by(task_id=handler_task.id).count(),
            1,
        )

    def test_expired_designated_assignment_marks_task_for_reassignment(self):
        expired_assignment = self.add_assignment(
            "expired-leader", "Expired Leader", "supply.company_leader",
            valid_until=date(2026, 8, 11),
        )
        self.db.commit()
        self.designated_task.designated_user_id = expired_assignment.user_id
        self.designated_task.designated_assignment_id = expired_assignment.id
        self.db.commit()
        refresh_invalid_designated_tasks(self.db, on_date=date(2026, 8, 12))
        self.assertEqual(
            self.db.get(WorkflowTask, self.designated_task.id).status,
            WorkflowTaskStatus.AWAITING_REASSIGNMENT,
        )

    def test_inactive_non_designated_requester_refreshes_invalid_designated_task(self):
        self.leader.assignments[0].valid_until = date.today() - timedelta(days=1)
        self.leader_b.is_active = False
        self.db.commit()
        self.assertFalse(task_is_actionable_by(self.db, self.designated_task, self.leader_b))
        self.assertEqual(
            self.db.get(WorkflowTask, self.designated_task.id).status,
            WorkflowTaskStatus.AWAITING_REASSIGNMENT,
        )

    def test_inbox_returns_only_actionable_active_tasks(self):
        self.shared_task.status = WorkflowTaskStatus.ACTIVE
        self.db.commit()
        self.assertEqual(
            [task.id for task in my_active_tasks(self.db, self.reviewer_a)],
            [self.shared_task.id],
        )
        self.assertEqual(
            [task.id for task in my_active_tasks(self.db, self.leader)],
            [self.designated_task.id],
        )
        business = ApprovalForm(
            form_type=ContractType.BUSINESS,
            created_by=self.handler.id,
        )
        payment = ApprovalForm(
            form_type=ContractType.PAYMENT,
            created_by=self.handler.id,
        )
        self.db.add_all([business, payment])
        self.db.commit()
        business_instance = start_workflow(
            self.db,
            WorkflowTargetType.BUSINESS_APPROVAL,
            business.id,
            self.handler,
            {
                "company_leader": self.leader.id,
                "supply_governance_leader": self.governance.id,
            },
        )
        payment_instance = start_workflow(
            self.db,
            WorkflowTargetType.PAYMENT_APPROVAL,
            payment.id,
            self.handler,
            {
                "company_leader": self.leader.id,
                "supply_governance_leader": self.governance.id,
            },
        )
        business_instance.submitted_at = self.instance.submitted_at - timedelta(seconds=1)
        payment_instance.submitted_at = self.instance.submitted_at
        self.db.commit()
        business_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == business_instance.id,
            WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
        ))
        payment_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == payment_instance.id,
            WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
        ))

        admin_tasks = my_active_tasks(self.db, self.admin)
        self.assertEqual(
            [task.id for task in admin_tasks],
            [
                business_task.id,
                self.designated_task.id,
                payment_task.id,
                self.shared_task.id,
            ],
        )
        self.assertEqual(
            {task.id for task in admin_tasks},
            {
                business_task.id,
                self.designated_task.id,
                payment_task.id,
                self.shared_task.id,
            },
        )

    def test_superuser_approval_records_real_actor_and_system_governance_snapshot(self):
        complete_task(
            self.db,
            self.designated_task.id,
            self.admin,
            WorkflowAction.APPROVE,
            "admin test approval",
        )
        action = self.db.scalar(select(WorkflowTaskAction).where(
            WorkflowTaskAction.task_id == self.designated_task.id,
        ))

        self.assertEqual(action.actor_id, self.admin.id)
        self.assertEqual(action.actor_name, self.admin.full_name)
        self.assertEqual(action.organization_code, "system.governance")
        self.assertEqual(action.organization_name, "系统治理")
        self.assertEqual(action.position_code, "system.superuser")
        self.assertEqual(action.position_name, "超级管理员")
        self.assertEqual(action.signature_snapshot, self.admin.signature)
        self.assertEqual(
            self.db.scalar(select(UserAssignment).where(
                UserAssignment.user_id == self.admin.id,
            )),
            None,
        )

    def test_enabled_superuser_receives_all_active_task_counts(self):
        business = ApprovalForm(
            form_type=ContractType.BUSINESS,
            created_by=self.handler.id,
        )
        self.db.add(business)
        self.db.commit()
        start_workflow(
            self.db,
            WorkflowTargetType.BUSINESS_APPROVAL,
            business.id,
            self.handler,
            {
                "company_leader": self.leader.id,
                "supply_governance_leader": self.governance.id,
            },
        )
        self.db.commit()

        self.assertEqual(
            actionable_active_task_counts(self.db, self.admin),
            {
                WorkflowTargetType.CONTRACT: 1,
                WorkflowTargetType.BUSINESS_APPROVAL: 1,
            },
        )
        self.admin.is_active = False
        self.db.commit()
        self.assertEqual(actionable_active_task_counts(self.db, self.admin), {})

    def test_complete_and_return_moves_between_adjacent_nodes_with_snapshots(self):
        complete_task(self.db, self.designated_task.id, self.leader, WorkflowAction.APPROVE, "approved")
        legal_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == self.instance.id,
            WorkflowTask.sequence == 2,
        ))
        complete_task(self.db, legal_task.id, self.legal, WorkflowAction.APPROVE, "approved")
        risk_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == self.instance.id,
            WorkflowTask.sequence == 3,
        ))
        self.assertEqual(risk_task.status, WorkflowTaskStatus.ACTIVE)
        complete_task(self.db, risk_task.id, self.reviewer_a, WorkflowAction.RETURN, "needs revision")
        self.db.refresh(legal_task)
        self.db.refresh(risk_task)
        self.assertEqual(legal_task.status, WorkflowTaskStatus.ACTIVE)
        self.assertEqual(risk_task.status, WorkflowTaskStatus.RETURNED)
        action = self.db.scalar(select(WorkflowTaskAction).where(
            WorkflowTaskAction.task_id == risk_task.id,
            WorkflowTaskAction.action == WorkflowAction.RETURN,
        ))
        self.assertEqual(action.returned_to_sequence, legal_task.sequence)
        self.assertEqual(action.position_code, "investment.duty.supply_risk_review")
        projection = self.db.scalar(
            select(Approval).where(Approval.workflow_task_action_id == action.id)
        )
        self.assertEqual(projection.action.value, "reject")
        self.assertEqual(projection.position_code, action.position_code)

        complete_task(self.db, legal_task.id, self.legal, WorkflowAction.APPROVE, "approved again")
        self.db.refresh(risk_task)
        self.assertEqual(risk_task.status, WorkflowTaskStatus.ACTIVE)
        self.assertIsNone(risk_task.completed_at)
        complete_task(self.db, risk_task.id, self.reviewer_b, WorkflowAction.APPROVE, "approved")
        actions = list(self.db.scalars(
            select(WorkflowTaskAction)
            .where(WorkflowTaskAction.task_id == risk_task.id)
            .order_by(WorkflowTaskAction.id)
        ))
        self.assertEqual(
            [item.action for item in actions],
            [WorkflowAction.RETURN, WorkflowAction.APPROVE],
        )

    def test_return_to_handler_can_resubmit_same_instance_with_full_history(self):
        original_instance_id = self.instance.id
        complete_task(
            self.db,
            self.designated_task.id,
            self.leader,
            WorkflowAction.RETURN,
            "handler changes required",
        )
        handler_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == original_instance_id,
            WorkflowTask.sequence == 0,
        ))
        self.db.refresh(self.contract)
        self.assertEqual(handler_task.status, WorkflowTaskStatus.ACTIVE)
        self.assertEqual(self.contract.status, ContractStatus.REJECTED)
        self.assertEqual(self.contract.current_step, 0)

        complete_task(
            self.db,
            handler_task.id,
            self.handler,
            WorkflowAction.SUBMIT,
            "resubmitted",
        )
        self.db.refresh(self.designated_task)
        self.db.refresh(self.contract)
        self.assertEqual(self.designated_task.status, WorkflowTaskStatus.ACTIVE)
        self.assertEqual(self.contract.status, ContractStatus.PENDING)
        self.assertEqual(self.contract.workflow_instance_id, original_instance_id)
        self.assertEqual(self.db.query(WorkflowInstance).count(), 1)
        actions = list(self.db.scalars(
            select(WorkflowTaskAction)
            .where(WorkflowTaskAction.task_id == handler_task.id)
            .order_by(WorkflowTaskAction.id)
        ))
        self.assertEqual(
            [item.action for item in actions],
            [WorkflowAction.SUBMIT, WorkflowAction.SUBMIT],
        )

    def test_superuser_can_resubmit_another_users_active_handler_task(self):
        original_instance_id = self.instance.id
        complete_task(
            self.db,
            self.designated_task.id,
            self.leader,
            WorkflowAction.RETURN,
            "handler changes required",
        )
        handler_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == original_instance_id,
            WorkflowTask.sequence == 0,
        ))

        complete_task(
            self.db,
            handler_task.id,
            self.admin,
            WorkflowAction.SUBMIT,
            "admin resubmission",
        )

        action = self.db.scalar(
            select(WorkflowTaskAction)
            .where(
                WorkflowTaskAction.task_id == handler_task.id,
                WorkflowTaskAction.action == WorkflowAction.SUBMIT,
            )
            .order_by(WorkflowTaskAction.id.desc())
        )
        self.db.refresh(self.designated_task)
        self.assertEqual(self.designated_task.status, WorkflowTaskStatus.ACTIVE)
        self.assertEqual(action.actor_id, self.admin.id)
        self.assertEqual(action.organization_code, "system.governance")
        self.assertEqual(action.position_code, "system.superuser")

    def test_return_to_expired_designated_assignment_awaits_reassignment(self):
        complete_task(self.db, self.designated_task.id, self.leader, WorkflowAction.APPROVE, "approved")
        legal_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == self.instance.id,
            WorkflowTask.sequence == 2,
        ))
        complete_task(self.db, legal_task.id, self.legal, WorkflowAction.APPROVE, "approved")
        expired_assignment = self.legal.assignments[0]
        expired_assignment.valid_until = date.today() - timedelta(days=1)
        self.db.commit()
        risk_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == self.instance.id,
            WorkflowTask.sequence == 3,
        ))
        complete_task(self.db, risk_task.id, self.reviewer_a, WorkflowAction.RETURN, "needs reassignment")
        self.db.refresh(legal_task)
        self.db.refresh(self.instance)
        self.assertEqual(legal_task.status, WorkflowTaskStatus.AWAITING_REASSIGNMENT)
        self.assertEqual(self.instance.current_sequence, legal_task.sequence)

    def test_completion_conflict_preserves_parent_transaction_and_pending_objects(self):
        task_id = self.designated_task.id
        complete_task(
            self.db,
            task_id,
            self.leader,
            WorkflowAction.APPROVE,
            "winner",
        )
        pending = User(
            username="pending-completion-conflict",
            full_name="Pending Completion Conflict",
            hashed_password="test",
        )
        self.db.add(pending)

        with self.assertRaises(WorkflowTaskConflict) as raised:
            complete_task(
                self.db,
                task_id,
                self.leader_b,
                WorkflowAction.APPROVE,
                "loser",
            )

        self.assertEqual(raised.exception.code, "task_already_completed")
        self.assertEqual(raised.exception.actor_name, self.leader.full_name)
        self.assertEqual(raised.exception.action, WorkflowAction.APPROVE.value)
        self.assertIsInstance(raised.exception.completed_at, datetime)
        self.assertTrue(self.db.in_transaction())
        self.assertIn(pending, self.db.new)
        self.assertIsNone(pending.id)
        self.db.commit()
        self.assertIsNotNone(self.db.scalar(
            select(User).where(User.username == "pending-completion-conflict")
        ))

    def test_non_sqlite_conflict_prefers_uncommitted_same_transaction_winner(self):
        task_id = self.designated_task.id
        complete_task(
            self.db,
            task_id,
            self.leader,
            WorkflowAction.APPROVE,
            "uncommitted winner",
        )
        isolated_engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(isolated_engine)
        non_sqlite_connection = SimpleNamespace(
            dialect=SimpleNamespace(name="mysql"),
            engine=isolated_engine,
        )
        try:
            conflict = _load_task_conflict_after_rollback(
                self.db,
                non_sqlite_connection,
                task_id,
            )
        finally:
            isolated_engine.dispose()

        self.assertEqual(conflict.actor_name, self.leader.full_name)
        self.assertEqual(conflict.action, WorkflowAction.APPROVE.value)
        self.assertIsInstance(conflict.completed_at, datetime)
        self.db.rollback()

    def test_success_does_not_autoflush_parent_and_rolls_back_with_caller(self):
        task_id = self.designated_task.id
        instance_id = self.instance.id
        self.db.expunge(self.instance)
        pending = User(
            username="pending-completion-success",
            full_name="Pending Completion Success",
            hashed_password="test",
        )
        self.db.add(pending)

        complete_task(
            self.db,
            task_id,
            self.leader,
            WorkflowAction.APPROVE,
            "caller owns transaction",
        )

        self.assertIn(pending, self.db.new)
        self.assertIsNone(pending.id)
        self.db.expunge(pending)
        self.db.rollback()
        with Session(self.engine) as verification:
            task = verification.get(WorkflowTask, task_id)
            next_task = verification.scalar(select(WorkflowTask).where(
                WorkflowTask.instance_id == instance_id,
                WorkflowTask.sequence == 2,
            ))
            self.assertEqual(task.status, WorkflowTaskStatus.ACTIVE)
            self.assertEqual(task.version, 0)
            self.assertIsNone(task.completed_at)
            self.assertEqual(next_task.status, WorkflowTaskStatus.PENDING)
            self.assertEqual(verification.scalar(
                select(func.count())
                .select_from(WorkflowTaskAction)
                .where(
                    WorkflowTaskAction.task_id == task_id,
                    WorkflowTaskAction.action == WorkflowAction.APPROVE,
                )
            ), 0)


class WorkflowConcurrencyTest(unittest.TestCase):
    add_user = WorkflowStartTest.add_user
    add_assignment = WorkflowStartTest.add_assignment
    designated_users = WorkflowStartTest.designated_users

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "workflow-concurrency.db"
        self.engine = create_engine(
            f"sqlite+pysqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.users = {}
        self.publisher = self.add_user("publisher", "Publisher")
        self.handler = self.add_assignment(
            "handler", "Handler", "supply.business_handler"
        ).user
        self.leader = self.add_assignment(
            "leader", "Amy Leader", "supply.company_leader"
        ).user
        self.legal = self.add_assignment(
            "legal", "Bob Legal", "external.legal_counsel", external_scope=True
        ).user
        self.governance = self.add_assignment(
            "governance", "Cara Governance", "governance.supply_leader"
        ).user
        self.reviewer_a = self.add_assignment(
            "reviewer-a", "Reviewer A", "investment.duty.supply_risk_review"
        ).user
        self.reviewer_b = self.add_assignment(
            "reviewer-b", "Reviewer B", "investment.duty.supply_risk_review"
        ).user
        self.db.commit()
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        contract = Contract(
            contract_no="TASK5-CONCURRENT",
            title="Task 5 Concurrent Contract",
            created_by=self.handler.id,
        )
        self.db.add(contract)
        self.db.commit()
        instance = start_workflow(
            self.db,
            WorkflowTargetType.CONTRACT,
            contract.id,
            self.handler,
            self.designated_users(),
        )
        self.db.commit()
        self.instance_id = instance.id
        self.contract_id = contract.id
        leader_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.sequence == 1,
        ))
        complete_task(self.db, leader_task.id, self.leader, WorkflowAction.APPROVE, "approved")
        self.db.commit()
        legal_task = self.db.scalar(select(WorkflowTask).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.sequence == 2,
        ))
        complete_task(self.db, legal_task.id, self.legal, WorkflowAction.APPROVE, "approved")
        self.db.commit()
        self.task_id = self.db.scalar(select(WorkflowTask.id).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.sequence == 3,
        ))
        self.next_task_id = self.db.scalar(select(WorkflowTask.id).where(
            WorkflowTask.instance_id == instance.id,
            WorkflowTask.sequence == 4,
        ))
        self.next_task_version = self.db.get(WorkflowTask, self.next_task_id).version
        self.actor_ids = (self.reviewer_a.id, self.reviewer_b.id)
        self.db.close()

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_two_shared_actors_can_only_complete_once(self):
        barrier = threading.Barrier(2)
        results = []

        def act(user_id):
            with Session(self.engine) as session:
                actor = session.get(User, user_id)
                barrier.wait()
                try:
                    complete_task(
                        session,
                        self.task_id,
                        actor,
                        WorkflowAction.APPROVE,
                        "",
                    )
                    session.commit()
                    results.append(("approved", actor.full_name))
                except WorkflowTaskConflict as error:
                    results.append((
                        "conflict",
                        error.actor_name,
                        error.action,
                        error.completed_at,
                    ))

        threads = [threading.Thread(target=act, args=(user_id,)) for user_id in self.actor_ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertCountEqual([item[0] for item in results], ["approved", "conflict"])
        winner = next(item for item in results if item[0] == "approved")
        conflict = next(item for item in results if item[0] == "conflict")
        self.assertEqual(conflict[1], winner[1])
        self.assertEqual(conflict[2], WorkflowAction.APPROVE.value)
        self.assertIsInstance(conflict[3], datetime)
        with Session(self.engine) as session:
            count = session.scalar(
                select(func.count())
                .select_from(WorkflowTaskAction)
                .where(
                    WorkflowTaskAction.task_id == self.task_id,
                    WorkflowTaskAction.action == WorkflowAction.APPROVE,
                )
            )
            self.assertEqual(count, 1)
            next_task = session.get(WorkflowTask, self.next_task_id)
            instance = session.get(WorkflowInstance, self.instance_id)
            contract = session.get(Contract, self.contract_id)
            self.assertEqual(next_task.status, WorkflowTaskStatus.ACTIVE)
            self.assertEqual(next_task.version, self.next_task_version + 1)
            self.assertEqual(instance.status, WorkflowInstanceStatus.ACTIVE)
            self.assertEqual(instance.current_sequence, next_task.sequence)
            self.assertEqual(contract.status, ContractStatus.PENDING)
            self.assertEqual(contract.current_step, next_task.sequence)


class WorkflowPublicationContinuationTest(unittest.TestCase):
    setUp = WorkflowPublicationTest.setUp
    tearDown = WorkflowPublicationTest.tearDown
    add_assignment = WorkflowPublicationTest.add_assignment
    version = WorkflowPublicationTest.version
    assert_parent_pending_unflushed = WorkflowPublicationTest.assert_parent_pending_unflushed

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
