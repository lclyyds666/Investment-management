import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.enums import CompanyCode, ResourceCode, Role
from app.models.portal import UserCompanyRole
from app.services.permissions import allowed_resources, get_company_role, has_resource


class CompanyRoleModelTest(unittest.TestCase):
    def test_company_and_resource_codes_are_stable(self):
        self.assertEqual(CompanyCode.INVESTMENT.value, "investment")
        self.assertEqual(CompanyCode.SUPPLY_MANAGEMENT.value, "supplymanagement")
        self.assertEqual(CompanyCode.FUND_MANAGEMENT.value, "fundmanagement")
        self.assertEqual(ResourceCode.SCENIC_ANALYTICS.value, "supply.scenic.analytics")

    def test_user_company_role_has_one_membership_per_company(self):
        unique_sets = {
            tuple(column.name for column in constraint.columns)
            for constraint in UserCompanyRole.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("user_id", "company_code"), unique_sets)


class CompanyPermissionServiceTest(unittest.TestCase):
    def test_supply_membership_overrides_stale_legacy_role(self):
        user = SimpleNamespace(id=7, role=Role.LEGAL_COUNSEL, is_superuser=False)
        db = Mock()
        db.scalar.return_value = Role.BUSINESS_HANDLER
        self.assertEqual(
            get_company_role(db, user, CompanyCode.SUPPLY_MANAGEMENT),
            Role.BUSINESS_HANDLER,
        )

    def test_user_without_company_membership_has_no_supply_resource(self):
        user = SimpleNamespace(id=8, role=Role.BUSINESS_HANDLER, is_superuser=False)
        db = Mock()
        db.scalar.return_value = None
        self.assertFalse(
            has_resource(
                db,
                user,
                CompanyCode.SUPPLY_MANAGEMENT,
                ResourceCode.SCENIC_ANALYTICS,
            )
        )

    def test_superuser_has_all_registered_resources(self):
        user = SimpleNamespace(id=1, is_superuser=True)
        resources = allowed_resources(Mock(), user, CompanyCode.SUPPLY_MANAGEMENT)
        self.assertIn(ResourceCode.SUPPLY_ADMIN, resources)
        self.assertIn(ResourceCode.SCENIC_ANALYTICS, resources)


if __name__ == "__main__":
    unittest.main()
