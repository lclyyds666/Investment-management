import unittest
from datetime import date

from app.core.enums import (
    AssignmentStatus,
    CompanyCode,
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
from app.services.organization_catalog import ORGANIZATION_CATALOG, POSITION_CATALOG


class OrganizationModelContractTest(unittest.TestCase):
    def test_enum_values_are_stable(self):
        self.assertEqual(Role.UNASSIGNED.value, "unassigned")
        self.assertEqual(OrganizationType.COMPANY.value, "company")
        self.assertEqual(PositionCategory.GOVERNANCE.value, "governance")
        self.assertEqual(PermissionAction.APPROVE.value, "approve")
        self.assertEqual(DataScope.ASSIGNED.value, "assigned")
        self.assertEqual(AssignmentStatus.ACTIVE.value, "active")
        self.assertEqual(CompanyCode.ZHANWEI.value, "zhanwei")
        self.assertEqual(CompanyCode.XINHUA_PROPERTY.value, "xinhuaproperty")

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

    def test_legal_subsidiaries_and_position_names_are_canonical(self):
        organizations = {item["code"]: item for item in ORGANIZATION_CATALOG}
        positions = {item["code"]: item for item in POSITION_CATALOG}

        self.assertEqual(organizations["zhanwei"]["name"], "山东展威科技有限公司")
        self.assertEqual(organizations["zhanwei"]["parent"], "investment")
        self.assertEqual(organizations["xinhuaproperty"]["name"], "山东新华置业有限公司")
        self.assertEqual(organizations["xinhuaproperty"]["parent"], "investment")
        self.assertEqual(positions["investment.department.director"]["name"], "部门主任")
        self.assertEqual(positions["investment.department.deputy_director"]["name"], "部门副主任")
        self.assertEqual(positions["supply.company_leader"]["name"], "供管公司负责人")
        self.assertEqual(positions["governance.supply_leader"]["name"], "供管公司分管领导")
        self.assertNotIn("业务经办", {item["name"] for item in POSITION_CATALOG})
        self.assertNotIn("业务复核", {item["name"] for item in POSITION_CATALOG})
