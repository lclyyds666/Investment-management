import unittest
from datetime import date

from app.core.enums import (
    AssignmentStatus,
    DataScope,
    OrganizationType,
    PermissionAction,
    PositionCategory,
    Role,
)
from app.models.organization import (
    ExternalAssignment,
    GovernanceScope,
    Organization,
    Permission,
    Position,
    PositionPermission,
    UserAssignment,
)


class OrganizationModelContractTest(unittest.TestCase):
    def test_enum_values_are_stable(self):
        self.assertEqual(Role.UNASSIGNED.value, "unassigned")
        self.assertEqual(OrganizationType.COMPANY.value, "company")
        self.assertEqual(PositionCategory.GOVERNANCE.value, "governance")
        self.assertEqual(PermissionAction.APPROVE.value, "approve")
        self.assertEqual(DataScope.ASSIGNED.value, "assigned")
        self.assertEqual(AssignmentStatus.ACTIVE.value, "active")

    def test_core_table_names_are_stable(self):
        self.assertEqual(Organization.__tablename__, "sys_organization")
        self.assertEqual(Position.__tablename__, "sys_position")
        self.assertEqual(UserAssignment.__tablename__, "sys_user_assignment")
        self.assertEqual(Permission.__tablename__, "sys_permission")
        self.assertEqual(PositionPermission.__tablename__, "sys_position_permission")
        self.assertEqual(GovernanceScope.__tablename__, "sys_governance_scope")
        self.assertEqual(ExternalAssignment.__tablename__, "sys_external_assignment")

    def test_assignment_supports_multiple_positions_in_one_company(self):
        constraints = {
            constraint.name
            for constraint in UserAssignment.__table__.constraints
            if constraint.name
        }
        self.assertNotIn("uq_user_assignment_company", constraints)

    def test_assignment_period_is_inclusive(self):
        assignment = UserAssignment(
            user_id=7,
            organization_id=2,
            position_id=3,
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            status=AssignmentStatus.ACTIVE,
        )
        self.assertTrue(assignment.is_effective_on(date(2026, 12, 31)))
        self.assertFalse(assignment.is_effective_on(date(2027, 1, 1)))
