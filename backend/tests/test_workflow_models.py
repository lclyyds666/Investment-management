import unittest
from pathlib import Path

from app.core.enums import (
    WorkflowAction,
    WorkflowAssigneeMode,
    WorkflowInstanceStatus,
    WorkflowTargetType,
    WorkflowTaskStatus,
    WorkflowVersionStatus,
)
from app.models.approval import Approval
from app.models.approval_form import ApprovalForm, ApprovalFormAction
from app.models.contract import Contract
from app.models.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowNode,
    WorkflowTask,
    WorkflowTaskAction,
    WorkflowVersion,
)


def unique_constraint_names(model):
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }


class WorkflowModelContractTest(unittest.TestCase):
    def test_table_names_are_stable(self):
        self.assertEqual(WorkflowDefinition.__tablename__, "wf_definition")
        self.assertEqual(WorkflowVersion.__tablename__, "wf_version")
        self.assertEqual(WorkflowNode.__tablename__, "wf_node")
        self.assertEqual(WorkflowInstance.__tablename__, "wf_instance")
        self.assertEqual(WorkflowTask.__tablename__, "wf_task")
        self.assertEqual(WorkflowTaskAction.__tablename__, "wf_task_action")

    def test_modes_statuses_and_actions_are_stable(self):
        self.assertEqual(WorkflowTargetType.PAYMENT_APPROVAL.value, "payment_approval")
        self.assertEqual(WorkflowVersionStatus.PUBLISHED.value, "published")
        self.assertEqual(WorkflowInstanceStatus.CANCELLED.value, "cancelled")
        self.assertEqual(WorkflowAssigneeMode.SHARED_POSITION.value, "shared_position")
        self.assertEqual(WorkflowAssigneeMode.DESIGNATED_USER.value, "designated_user")
        self.assertEqual(
            WorkflowTaskStatus.AWAITING_REASSIGNMENT.value,
            "awaiting_reassignment",
        )
        self.assertEqual(WorkflowAction.REASSIGN.value, "reassign")

    def test_definition_version_and_node_uniqueness(self):
        self.assertIn("uq_workflow_version_definition_version", unique_constraint_names(WorkflowVersion))
        self.assertIn("uq_workflow_node_version_sequence", unique_constraint_names(WorkflowNode))
        self.assertIn("uq_workflow_node_version_code", unique_constraint_names(WorkflowNode))

    def test_runtime_uniqueness_and_optimistic_version(self):
        self.assertIn("uq_workflow_instance_target", unique_constraint_names(WorkflowInstance))
        self.assertIn("uq_workflow_task_instance_node", unique_constraint_names(WorkflowTask))
        self.assertEqual(WorkflowTask.__table__.c.version.default.arg, 0)

    def test_runtime_foreign_keys_cover_assignments_and_users(self):
        targets = {
            foreign_key.target_fullname
            for foreign_key in WorkflowTask.__table__.foreign_keys
        }
        self.assertIn("sys_user.id", targets)
        self.assertIn("sys_user_assignment.id", targets)

    def test_workflow_nodes_persist_dynamic_candidate_rules(self):
        columns = WorkflowNode.__table__.columns
        self.assertEqual(columns.candidate_rule.type.length, 32)
        self.assertFalse(columns.candidate_rule.nullable)
        self.assertEqual(columns.candidate_rule.default.arg, "position")
        self.assertIn("candidate_position_codes", columns)

    def test_reassignment_names_are_nullable_immutable_snapshots(self):
        columns = WorkflowTaskAction.__table__.columns
        self.assertIn("previous_assignee_name", columns)
        self.assertIn("new_assignee_name", columns)
        self.assertTrue(columns.previous_assignee_name.nullable)
        self.assertTrue(columns.new_assignee_name.nullable)
        self.assertEqual(columns.previous_assignee_name.type.length, 128)
        self.assertEqual(columns.new_assignee_name.type.length, 128)
        self.assertEqual(WorkflowTask.__table__.c.required_position_name.type.length, 128)
        self.assertFalse(WorkflowTask.__table__.c.required_position_name.nullable)

    def test_business_models_keep_legacy_fields_and_add_links(self):
        self.assertTrue({"status", "current_step", "workflow_instance_id"}.issubset(Contract.__table__.columns.keys()))
        self.assertTrue({"status", "current_step", "workflow_instance_id"}.issubset(ApprovalForm.__table__.columns.keys()))
        for model in (Approval, ApprovalFormAction):
            columns = set(model.__table__.columns.keys())
            self.assertTrue({
                "workflow_task_action_id",
                "organization_code",
                "organization_name",
                "position_code",
                "position_name",
            }.issubset(columns))

    def test_init_db_registers_workflow_models(self):
        source = Path("app/db/init_db.py").read_text(encoding="utf-8")
        self.assertIn("from app.models.workflow import", source)

    def test_migration_has_static_orm_parity_and_idempotent_guards(self):
        source = Path("migrations/20260814_position_workflow_engine.sql").read_text(encoding="utf-8")
        models = (
            WorkflowDefinition,
            WorkflowVersion,
            WorkflowNode,
            WorkflowInstance,
            WorkflowTask,
            WorkflowTaskAction,
        )
        for model in models:
            table_name = model.__tablename__
            self.assertIn(f"CREATE TABLE IF NOT EXISTS `{table_name}`", source)
            for column_name in model.__table__.columns.keys():
                if model is WorkflowNode and column_name in {
                    "candidate_rule",
                    "candidate_position_codes",
                }:
                    continue
                self.assertIn(f"`{column_name}`", source, f"{table_name}.{column_name}")
        for table_name, column_name in (
            ("biz_contract", "workflow_instance_id"),
            ("biz_approval_form", "workflow_instance_id"),
            ("biz_approval", "workflow_task_action_id"),
            ("biz_approval_form_action", "workflow_task_action_id"),
        ):
            self.assertIn(f"table_name = '{table_name}' AND column_name = '{column_name}'", source)
        self.assertIn("information_schema.statistics", source)
        self.assertIn("information_schema.table_constraints", source)
        for column_name in ("previous_assignee_name", "new_assignee_name"):
            self.assertIn(
                f"table_name = 'wf_task_action' AND column_name = '{column_name}'",
                source,
            )

    def test_unified_organization_tables_use_production_collation(self):
        source = Path(
            "migrations/20260813_unified_organization_permissions.sql"
        ).read_text(encoding="utf-8")
        for table_name in (
            "sys_organization",
            "sys_position",
            "sys_permission",
            "sys_user_assignment",
            "sys_position_permission",
            "sys_governance_scope",
            "sys_external_assignment",
        ):
            marker = f"CREATE TABLE IF NOT EXISTS `{table_name}` ("
            statement_start = source.index(marker)
            statement_end = source.index(";", statement_start)
            statement = source[statement_start : statement_end + 1]
            self.assertIn(
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
                "COLLATE=utf8mb4_unicode_ci",
                statement,
                table_name,
            )


if __name__ == "__main__":
    unittest.main()
