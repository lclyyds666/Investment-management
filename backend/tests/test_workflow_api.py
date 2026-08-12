import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.init_db  # noqa: F401
from app.api.deps import get_current_user
from app.core.enums import AssignmentStatus, ContractStatus, WorkflowAction, WorkflowTaskStatus
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.approval import Approval
from app.models.contract import Contract
from app.models.approval_form import ApprovalForm
from app.models.organization import ExternalAssignment, Organization, Position, UserAssignment
from app.models.user import User
from app.models.workflow import WorkflowTask, WorkflowTaskAction
from app.services.organization_catalog import seed_authorization_catalog
from app.services.workflow_engine import seed_workflow_definitions, start_workflow


class WorkflowApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.publisher = self.add_user("publisher", "Publisher")
        self.handler = self.add_user("handler", "Handler")
        self.reviewer_a = self.add_user("reviewer-a", "Reviewer A")
        self.reviewer_b = self.add_user("reviewer-b", "Reviewer B")
        self.leader = self.add_user("leader", "Leader")
        self.other_leader = self.add_user("other-leader", "Other Leader")
        self.legal = self.add_user("legal", "Legal")
        self.risk = self.add_user("risk", "Risk")
        self.governance = self.add_user("governance", "Governance")
        self.admin = self.add_user("admin", "Information Maintainer", is_superuser=True)
        self.assign(self.handler, "supplymanagement", "supply.business_handler")
        self.assign(self.reviewer_a, "supplymanagement", "supply.business_reviewer")
        self.assign(self.reviewer_b, "supplymanagement", "supply.business_reviewer")
        self.assign(self.leader, "supplymanagement", "supply.company_leader")
        self.assign(self.other_leader, "supplymanagement", "supply.company_leader")
        legal_assignment = self.assign(self.legal, "external.legal", "external.legal_counsel")
        self.db.add(ExternalAssignment(
            assignment_id=legal_assignment.id,
            provider_name="Legal Firm",
            service_scopes=["contract_legal_review"],
        ))
        self.assign(self.risk, "investment.legal_risk", "investment.duty.supply_risk_review")
        self.assign(self.governance, "supplymanagement", "governance.supply_leader")
        seed_workflow_definitions(self.db, self.publisher.id)
        self.db.commit()
        self.contract = Contract(
            contract_no="WF-API-1",
            title="Workflow API Contract",
            status=ContractStatus.DRAFT,
            created_by=self.handler.id,
        )
        self.db.add(self.contract)
        self.db.commit()
        self.instance = start_workflow(
            self.db,
            "contract",
            self.contract.id,
            self.handler,
            {
                "company_leader": self.leader.id,
                "legal_counsel": self.legal.id,
                "supply_governance_leader": self.governance.id,
            },
        )
        self.db.commit()
        self.app = create_app()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.current_user = self.handler
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def add_user(self, username, full_name, *, is_superuser=False):
        user = User(
            username=username,
            full_name=full_name,
            hashed_password="test",
            is_superuser=is_superuser,
            is_active=True,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def assign(self, user, organization_code, position_code, *, valid_until=None, status=AssignmentStatus.ACTIVE):
        assignment = UserAssignment(
            user_id=user.id,
            organization_id=self.db.scalar(select(Organization.id).where(Organization.code == organization_code)),
            position_id=self.db.scalar(select(Position.id).where(Position.code == position_code)),
            valid_from=date(2026, 1, 1),
            valid_until=valid_until,
            status=status,
        )
        self.db.add(assignment)
        self.db.flush()
        return assignment

    def active_task(self):
        return self.db.scalar(
            select(WorkflowTask).where(
                WorkflowTask.instance_id == self.instance.id,
                WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
            )
        )

    def test_candidates_require_submit_permission_and_filter_ineffective_assignments(self):
        expired = self.add_user("expired-leader", "Expired Leader")
        self.assign(expired, "supplymanagement", "supply.company_leader", valid_until=date.today() - timedelta(days=1))
        inactive = self.add_user("inactive-leader", "Inactive Leader")
        self.assign(inactive, "supplymanagement", "supply.company_leader", status=AssignmentStatus.INACTIVE)
        self.db.commit()

        response = self.client.get(
            "/api/v1/workflows/candidates",
            params={"workflow_code": "supply.contract.v2", "node_code": "company_leader"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        self.assertEqual(
            {item["user_id"] for item in response.json()["data"]},
            {self.leader.id, self.other_leader.id},
        )
        self.current_user = self.reviewer_a
        denied = self.client.get(
            "/api/v1/workflows/candidates",
            params={"workflow_code": "supply.contract.v2", "node_code": "company_leader"},
        )
        self.assertEqual(denied.status_code, 403)

    def test_inbox_exposes_shared_task_to_all_position_holders(self):
        payment = ApprovalForm(
            form_type="payment",
            contract_no="WF-API-PAYMENT",
            business_desc="Shared Inbox",
            status=ContractStatus.DRAFT,
            created_by=self.handler.id,
        )
        self.db.add(payment)
        self.db.commit()
        instance = start_workflow(
            self.db,
            "payment_approval",
            payment.id,
            self.handler,
            {
                "company_leader": self.leader.id,
                "supply_governance_leader": self.governance.id,
            },
        )
        self.db.commit()
        self.current_user = self.reviewer_a
        first = self.client.get("/api/v1/workflows/my-tasks")
        self.current_user = self.reviewer_b
        second = self.client.get("/api/v1/workflows/my-tasks")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["data"][0]["instance_id"], instance.id)
        self.assertEqual(second.json()["data"][0]["instance_id"], instance.id)
        self.assertIn("approve", first.json()["data"][0]["allowed_actions"])

    def test_designated_task_is_visible_and_actionable_only_by_selected_user(self):
        task = self.active_task()
        self.current_user = self.other_leader
        inbox = self.client.get("/api/v1/workflows/my-tasks")
        denied = self.client.post(f"/api/v1/workflows/tasks/{task.id}/approve", json={"comment": "no"})

        self.assertEqual(inbox.json()["data"], [])
        self.assertEqual(denied.status_code, 403)
        self.current_user = self.leader
        approved = self.client.post(f"/api/v1/workflows/tasks/{task.id}/approve", json={"comment": "ok"})
        self.assertEqual(approved.status_code, 200)

    def test_superuser_cannot_approve_and_second_action_returns_actor_snapshot(self):
        task = self.active_task()
        self.current_user = self.admin
        self.assertEqual(
            self.client.post(f"/api/v1/workflows/tasks/{task.id}/approve", json={"comment": "admin"}).status_code,
            403,
        )
        self.current_user = self.leader
        self.assertEqual(
            self.client.post(f"/api/v1/workflows/tasks/{task.id}/approve", json={"comment": "done"}).status_code,
            200,
        )
        self.current_user = self.other_leader
        conflict = self.client.post(f"/api/v1/workflows/tasks/{task.id}/approve", json={"comment": "late"})

        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"]["actor"], self.leader.full_name)
        self.assertEqual(conflict.json()["detail"]["action"], WorkflowAction.APPROVE.value)
        self.assertIsNotNone(conflict.json()["detail"]["completed_at"])
        self.assertEqual(
            self.db.scalar(select(WorkflowTaskAction.actor_name).where(WorkflowTaskAction.task_id == task.id)),
            self.leader.full_name,
        )
        self.current_user = self.handler
        self.assertEqual(
            self.client.get(
                "/api/v1/workflows/candidates",
                params={"workflow_code": "supply.contract.v2", "node_code": "company_leader"},
            ).status_code,
            200,
        )

    def test_reject_requires_nonblank_reason_and_timeline_preserves_snapshot(self):
        task = self.active_task()
        self.current_user = self.leader
        blank = self.client.post(f"/api/v1/workflows/tasks/{task.id}/reject", json={"reason": "   "})
        self.assertEqual(blank.status_code, 422)
        rejected = self.client.post(f"/api/v1/workflows/tasks/{task.id}/reject", json={"reason": "补充材料"})
        self.assertEqual(rejected.status_code, 200)
        timeline = self.client.get(f"/api/v1/workflows/instances/{self.instance.id}/timeline")
        self.assertEqual(timeline.status_code, 200)
        action = next(item for item in timeline.json()["data"] if item["action"] == "return")
        self.assertEqual(action["comment"], "补充材料")
        self.assertEqual(action["actor_name"], self.leader.full_name)

    def test_generic_workflow_actions_project_contract_approval_snapshots(self):
        submit_projection = self.db.scalar(
            select(Approval).where(Approval.contract_id == self.contract.id)
        )
        self.assertIsNotNone(submit_projection.workflow_task_action_id)
        self.assertEqual(submit_projection.approver_role, "supply.business_handler")
        self.assertEqual(submit_projection.position_code, "supply.business_handler")
        self.assertEqual(submit_projection.position_name, "业务经办")

        task = self.active_task()
        self.current_user = self.leader
        approved = self.client.post(
            f"/api/v1/workflows/tasks/{task.id}/approve",
            json={"comment": "同意"},
        )

        self.assertEqual(approved.status_code, 200)
        projection = self.db.scalar(
            select(Approval)
            .where(Approval.contract_id == self.contract.id)
            .order_by(Approval.id.desc())
        )
        self.assertEqual(projection.action.value, "approve")
        self.assertEqual(projection.position_code, "supply.company_leader")
        self.assertEqual(projection.position_name, "供应链公司负责人")
        self.assertEqual(projection.organization_code, "supplymanagement")

        legal_task = self.active_task()
        self.current_user = self.legal
        returned = self.client.post(
            f"/api/v1/workflows/tasks/{legal_task.id}/reject",
            json={"reason": "请补充"},
        )

        self.assertEqual(returned.status_code, 200)
        projection = self.db.scalar(
            select(Approval)
            .where(Approval.contract_id == self.contract.id)
            .order_by(Approval.id.desc())
        )
        self.assertEqual(projection.action.value, "reject")
        self.assertEqual(projection.position_code, "external.legal_counsel")


    def test_timeline_requires_target_view_permission_but_allows_information_maintainer(self):
        self.current_user = self.handler
        business_reader = self.client.get(f"/api/v1/workflows/instances/{self.instance.id}/timeline")
        self.assertEqual(business_reader.status_code, 200)
        self.current_user = self.publisher
        denied = self.client.get(f"/api/v1/workflows/instances/{self.instance.id}/timeline")
        self.assertEqual(denied.status_code, 403)
        self.current_user = self.admin
        allowed = self.client.get(f"/api/v1/workflows/instances/{self.instance.id}/timeline")
        self.assertEqual(allowed.status_code, 200)

    def test_reassignment_requires_superuser_reason_and_exact_effective_position(self):
        task = self.active_task()
        self.current_user = self.handler
        denied = self.client.post(
            f"/api/v1/workflows/tasks/{task.id}/reassign",
            json={"user_id": self.other_leader.id, "reason": "人员调整"},
        )
        self.assertEqual(denied.status_code, 403)
        self.current_user = self.admin
        blank = self.client.post(
            f"/api/v1/workflows/tasks/{task.id}/reassign",
            json={"user_id": self.other_leader.id, "reason": "   "},
        )
        self.assertEqual(blank.status_code, 422)
        wrong_position = self.client.post(
            f"/api/v1/workflows/tasks/{task.id}/reassign",
            json={"user_id": self.reviewer_a.id, "reason": "人员调整"},
        )
        self.assertEqual(wrong_position.status_code, 422)

        with patch.object(self.db, "commit", wraps=self.db.commit) as commit:
            response = self.client.post(
                f"/api/v1/workflows/tasks/{task.id}/reassign",
                json={"user_id": self.other_leader.id, "reason": "人员调整"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(commit.call_count, 1)
        self.db.expire_all()
        persisted = self.db.get(WorkflowTask, task.id)
        self.assertEqual(persisted.designated_user_id, self.other_leader.id)
        self.assertEqual(persisted.status, WorkflowTaskStatus.ACTIVE)
        snapshot = self.db.scalar(
            select(WorkflowTaskAction)
            .where(WorkflowTaskAction.task_id == task.id, WorkflowTaskAction.action == WorkflowAction.REASSIGN)
        )
        self.assertEqual(snapshot.previous_assignee_id, self.leader.id)
        self.assertEqual(snapshot.new_assignee_id, self.other_leader.id)
        self.assertEqual(snapshot.previous_assignee_name, "Leader")
        self.assertEqual(snapshot.new_assignee_name, "Other Leader")
        self.assertEqual(snapshot.reason, "人员调整")
        self.assertEqual(snapshot.actor_name, self.admin.full_name)
        self.leader.full_name = "Renamed Former Leader"
        self.other_leader.full_name = "Renamed New Leader"
        snapshot.previous_assignee_id = None
        snapshot.new_assignee_id = None
        self.db.commit()
        self.current_user = self.handler
        timeline = self.client.get(f"/api/v1/workflows/instances/{self.instance.id}/timeline")
        reassign_snapshot = next(
            item for item in timeline.json()["data"] if item["action"] == WorkflowAction.REASSIGN.value
        )
        self.assertIsNone(reassign_snapshot["previous_assignee_id"])
        self.assertIsNone(reassign_snapshot["new_assignee_id"])
        self.assertEqual(reassign_snapshot["previous_assignee_name"], "Leader")
        self.assertEqual(reassign_snapshot["new_assignee_name"], "Other Leader")

    def test_reassignment_cas_conflict_rolls_back_task_and_action_atomically(self):
        task = self.active_task()
        original = {
            "designated_user_id": task.designated_user_id,
            "designated_assignment_id": task.designated_assignment_id,
            "status": task.status,
            "version": task.version,
        }
        self.current_user = self.admin
        real_execute = self.db.execute

        def stale_task_update(statement, *args, **kwargs):
            result = real_execute(statement, *args, **kwargs)
            if getattr(statement, "is_update", False) and statement.table.name == "wf_task":
                return SimpleNamespace(rowcount=0)
            return result

        with patch.object(self.db, "execute", side_effect=stale_task_update):
            response = self.client.post(
                f"/api/v1/workflows/tasks/{task.id}/reassign",
                json={"user_id": self.other_leader.id, "reason": "并发改派"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "workflow_task_reassignment_conflict")
        self.db.expire_all()
        persisted = self.db.get(WorkflowTask, task.id)
        self.assertEqual(persisted.designated_user_id, original["designated_user_id"])
        self.assertEqual(persisted.designated_assignment_id, original["designated_assignment_id"])
        self.assertEqual(persisted.status, original["status"])
        self.assertEqual(persisted.version, original["version"])
        self.assertIsNone(self.db.scalar(
            select(WorkflowTaskAction).where(
                WorkflowTaskAction.task_id == task.id,
                WorkflowTaskAction.action == WorkflowAction.REASSIGN,
            )
        ))

    def test_reassignment_rejects_duplicate_person_and_shared_task(self):
        task = self.active_task()
        self.current_user = self.admin
        duplicate = self.client.post(
            f"/api/v1/workflows/tasks/{task.id}/reassign",
            json={"user_id": self.handler.id, "reason": "重复人员"},
        )
        self.assertEqual(duplicate.status_code, 422)

        task.assignee_mode = "shared_position"
        self.db.commit()
        shared = self.client.post(
            f"/api/v1/workflows/tasks/{task.id}/reassign",
            json={"user_id": self.other_leader.id, "reason": "错误模式"},
        )
        self.assertEqual(shared.status_code, 422)

    def test_reassignment_reactivates_invalid_designated_task_without_automatic_replacement(self):
        task = self.active_task()
        old_assignment = self.db.get(UserAssignment, task.designated_assignment_id)
        old_assignment.valid_until = date.today() - timedelta(days=1)
        self.db.commit()
        self.current_user = self.leader

        inbox = self.client.get("/api/v1/workflows/my-tasks")

        self.assertEqual(inbox.json()["data"], [])
        self.db.expire_all()
        self.assertEqual(self.db.get(WorkflowTask, task.id).status, WorkflowTaskStatus.AWAITING_REASSIGNMENT)
        self.assertEqual(self.db.get(WorkflowTask, task.id).designated_user_id, self.leader.id)
        self.current_user = self.admin
        response = self.client.post(
            f"/api/v1/workflows/tasks/{task.id}/reassign",
            json={"user_id": self.other_leader.id, "reason": "原任职失效"},
        )
        self.assertEqual(response.status_code, 200)
        self.db.expire_all()
        persisted = self.db.get(WorkflowTask, task.id)
        self.assertEqual(persisted.status, WorkflowTaskStatus.ACTIVE)
        self.assertEqual(persisted.designated_user_id, self.other_leader.id)


class ContractWorkflowApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.publisher = self.add_user("publisher", "Publisher")
        self.handler = self.add_user("contract-handler", "Contract Handler")
        self.leader = self.add_user("contract-leader", "Contract Leader")
        self.legal = self.add_user("contract-legal", "Contract Legal")
        self.risk = self.add_user("contract-risk", "Contract Risk")
        self.governance = self.add_user("contract-governance", "Contract Governance")
        self.assign(self.handler, "supplymanagement", "supply.business_handler")
        self.assign(self.leader, "supplymanagement", "supply.company_leader")
        legal_assignment = self.assign(self.legal, "external.legal", "external.legal_counsel")
        self.db.add(ExternalAssignment(
            assignment_id=legal_assignment.id,
            provider_name="Legal Firm",
            service_scopes=["contract_legal_review"],
        ))
        self.assign(self.risk, "investment.legal_risk", "investment.duty.supply_risk_review")
        self.assign(self.governance, "supplymanagement", "governance.supply_leader")
        seed_workflow_definitions(self.db, self.publisher.id)
        self.contract = Contract(
            contract_no="WF-CONTRACT-1",
            title="Contract Route Cutover",
            status=ContractStatus.DRAFT,
            created_by=self.handler.id,
        )
        self.db.add(self.contract)
        self.db.commit()
        self.current_user = self.handler
        self.app = create_app()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def add_user(self, username, full_name):
        user = User(
            username=username,
            full_name=full_name,
            hashed_password="test",
            is_active=True,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def assign(self, user, organization_code, position_code):
        assignment = UserAssignment(
            user_id=user.id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == organization_code)
            ),
            position_id=self.db.scalar(
                select(Position.id).where(Position.code == position_code)
            ),
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        )
        self.db.add(assignment)
        self.db.flush()
        return assignment

    def designation_payload(self):
        return {
            "designated_users": {
                "company_leader": self.leader.id,
                "legal_counsel": self.legal.id,
                "supply_governance_leader": self.governance.id,
            }
        }

    def test_contract_submit_requires_three_designated_users(self):
        response = self.client.post(
            f"/api/v1/contracts/{self.contract.id}/submit",
            json={"designated_users": {"company_leader": self.leader.id}},
        )
        self.assertEqual(response.status_code, 422)

    def test_contract_chain_uses_supply_governance_leader(self):
        response = self.client.post(
            f"/api/v1/contracts/{self.contract.id}/submit",
            json=self.designation_payload(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertIsNotNone(data["workflow_instance_id"])
        self.assertEqual(data["active_task"]["position_code"], "supply.company_leader")
        self.assertFalse(data["can_act"])
        tasks = list(self.db.scalars(
            select(WorkflowTask)
            .where(WorkflowTask.instance_id == data["workflow_instance_id"])
            .order_by(WorkflowTask.sequence)
        ))
        self.assertEqual(tasks[-1].required_position_code, "governance.supply_leader")

    def test_todo_and_legacy_wrappers_use_current_workflow_task(self):
        submitted = self.client.post(
            f"/api/v1/contracts/{self.contract.id}/submit",
            json=self.designation_payload(),
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.current_user = self.leader
        todo = self.client.get("/api/v1/contracts/todo")
        self.assertEqual([item["id"] for item in todo.json()["data"]], [self.contract.id])
        self.assertTrue(todo.json()["data"][0]["can_act"])
        approved = self.client.post(
            f"/api/v1/contracts/{self.contract.id}/approve",
            json={"comment": "负责人同意"},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["data"]["active_task"]["position_code"], "external.legal_counsel")
        self.current_user = self.legal
        returned = self.client.post(
            f"/api/v1/contracts/{self.contract.id}/reject",
            json={"comment": "退回补充"},
        )
        self.assertEqual(returned.status_code, 200, returned.text)
        self.assertEqual(returned.json()["data"]["active_task"]["position_code"], "supply.company_leader")
        self.current_user = self.handler
        timeline = self.client.get(
            f"/api/v1/workflows/instances/{self.contract.workflow_instance_id}/timeline"
        ).json()["data"]
        self.assertEqual(timeline[-1]["action"], "return")

    def test_legacy_reject_wrapper_requires_nonblank_reason(self):
        submitted = self.client.post(
            f"/api/v1/contracts/{self.contract.id}/submit",
            json=self.designation_payload(),
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.current_user = self.leader

        response = self.client.post(
            f"/api/v1/contracts/{self.contract.id}/reject",
            json={"comment": "   "},
        )

        self.assertEqual(response.status_code, 422)

    def test_external_legal_counsel_sees_only_designated_contract(self):
        other = Contract(
            contract_no="WF-CONTRACT-OTHER",
            title="Other Contract",
            status=ContractStatus.DRAFT,
            created_by=self.handler.id,
        )
        self.db.add(other)
        self.db.commit()
        submitted = self.client.post(
            f"/api/v1/contracts/{self.contract.id}/submit",
            json=self.designation_payload(),
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)

        self.current_user = self.legal
        listing = self.client.get("/api/v1/contracts")
        assigned = self.client.get(f"/api/v1/contracts/{self.contract.id}")
        unassigned = self.client.get(f"/api/v1/contracts/{other.id}")

        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual([item["id"] for item in listing.json()["data"]], [self.contract.id])
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(unassigned.status_code, 403)

    def test_external_legal_counsel_without_designation_sees_empty_list(self):
        self.current_user = self.legal

        response = self.client.get("/api/v1/contracts")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"], [])

    def test_legal_doc_uses_position_snapshots_and_historical_fallback(self):
        self.db.add_all([
            Approval(
                contract_id=self.contract.id,
                approver_id=self.legal.id,
                approver_role="ignored_for_new_row",
                action="approve",
                comment="法律意见",
                position_code="external.legal_counsel",
                position_name="外聘法律顾问",
            ),
            Approval(
                contract_id=self.contract.id,
                approver_id=self.risk.id,
                approver_role="risk_auditor",
                action="approve",
                comment="风控意见",
                position_code="investment.duty.supply_risk_review",
                position_name="供应链风控复核",
            ),
            Approval(
                contract_id=self.contract.id,
                approver_id=self.governance.id,
                approver_role="invest_director",
                action="approve",
                comment="历史治理意见",
            ),
        ])
        self.db.commit()

        with patch(
            "app.api.v1.endpoints.contract.legal_doc_svc.build_legal_doc",
            return_value=b"docx",
        ) as build:
            response = self.client.get(f"/api/v1/contracts/{self.contract.id}/legal-doc")

        self.assertEqual(response.status_code, 200, response.text)
        opinions = build.call_args.args[1]
        self.assertEqual(opinions["external.legal_counsel"]["comment"], "法律意见")
        self.assertEqual(
            opinions["investment.duty.supply_risk_review"]["comment"],
            "风控意见",
        )
        self.assertEqual(opinions["governance.supply_leader"]["comment"], "历史治理意见")


if __name__ == "__main__":
    unittest.main()
