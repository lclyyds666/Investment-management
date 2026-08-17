import unittest

from app.core.enums import Role
from app.services.legal_permissions import (
    LegalCapability,
    capabilities_for,
    capabilities_for_positions,
)


class LegalPermissionMatrixTest(unittest.TestCase):
    def test_business_and_risk_have_identical_permissions(self):
        self.assertEqual(
            capabilities_for(Role.BUSINESS_HANDLER),
            capabilities_for(Role.RISK_AUDITOR),
        )
        self.assertIn(LegalCapability.EDIT_CASE, capabilities_for(Role.BUSINESS_HANDLER))

    def test_management_role_is_read_only(self):
        capabilities = capabilities_for(Role.INVEST_DIRECTOR)
        self.assertIn(LegalCapability.VIEW_CASE, capabilities)
        self.assertIn(LegalCapability.VIEW_STATISTICS, capabilities)
        self.assertNotIn(LegalCapability.EDIT_CASE, capabilities)

    def test_superuser_has_maximum_permissions(self):
        capabilities = capabilities_for(None, is_superuser=True)
        self.assertEqual(capabilities, frozenset(LegalCapability))

    def test_counsel_cannot_manage_case_master_data(self):
        capabilities = capabilities_for(Role.LEGAL_COUNSEL)
        self.assertIn(LegalCapability.ADD_COUNSEL_CONTENT, capabilities)
        self.assertNotIn(LegalCapability.EDIT_CASE, capabilities)
        self.assertNotIn(LegalCapability.VIEW_STATISTICS, capabilities)

    def test_management_and_business_assignments_union_capabilities(self):
        capabilities = capabilities_for_positions({
            "investment.executive.general_manager",
            "investment.department.junior_manager",
        })

        self.assertIn(LegalCapability.EDIT_CASE, capabilities)
        self.assertIn(LegalCapability.EXPORT_MANAGEMENT, capabilities)


if __name__ == "__main__":
    unittest.main()
