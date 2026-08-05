import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.enums import CompanyCode, Role
from app.services.portal import applications_for_user, permission_snapshot_for_user


class PortalRegistryTest(unittest.TestCase):
    @patch("app.services.portal.get_company_role")
    def test_registry_always_returns_three_apps_in_fixed_order(self, company_role):
        company_role.side_effect = lambda db, user, company: (
            Role.BUSINESS_HANDLER if company == CompanyCode.SUPPLY_MANAGEMENT else None
        )

        apps = applications_for_user(Mock(), SimpleNamespace(is_superuser=False))

        self.assertEqual(
            [item.code for item in apps],
            ["investment", "supplymanagement", "fundmanagement"],
        )
        self.assertEqual(
            [item.status for item in apps],
            ["construction", "online", "construction"],
        )
        self.assertEqual([item.accessible for item in apps], [False, True, False])

    def test_product_name_is_unified(self):
        from app.core.config import Settings

        self.assertEqual(Settings().PROJECT_NAME, "山东出版投资有限公司工作平台")

    @patch("app.services.portal.get_company_role")
    def test_denied_applications_include_the_required_reason(self, company_role):
        company_role.return_value = None

        apps = applications_for_user(Mock(), SimpleNamespace(is_superuser=False))

        self.assertEqual(
            [item.denial_reason for item in apps],
            ["暂时无访问权限", "暂时无访问权限", "暂时无访问权限"],
        )


class PortalPermissionSnapshotTest(unittest.TestCase):
    @patch("app.services.portal.allowed_resources")
    @patch("app.services.portal.get_company_role")
    def test_snapshot_serializes_membership_roles_and_sorted_resource_codes(
        self, company_role, allowed_resources
    ):
        company_role.side_effect = lambda db, user, company: (
            Role.BUSINESS_HANDLER if company == CompanyCode.SUPPLY_MANAGEMENT else None
        )
        allowed_resources.return_value = frozenset()

        snapshot = permission_snapshot_for_user(
            Mock(), SimpleNamespace(is_superuser=False)
        )

        self.assertFalse(snapshot.is_superuser)
        self.assertEqual(
            snapshot.company_roles,
            {CompanyCode.SUPPLY_MANAGEMENT.value: Role.BUSINESS_HANDLER.value},
        )
        self.assertEqual(snapshot.resources, [])

    @patch("app.services.portal.allowed_resources")
    @patch("app.services.portal.get_company_role")
    def test_snapshot_sorts_resource_codes(self, company_role, allowed_resources):
        company_role.return_value = None
        allowed_resources.return_value = frozenset({
            "supply.operation", "supply.admin", "supply.dashboard"
        })

        snapshot = permission_snapshot_for_user(
            Mock(), SimpleNamespace(is_superuser=True)
        )

        self.assertTrue(snapshot.is_superuser)
        self.assertEqual(
            snapshot.resources,
            ["supply.admin", "supply.dashboard", "supply.operation"],
        )


if __name__ == "__main__":
    unittest.main()
