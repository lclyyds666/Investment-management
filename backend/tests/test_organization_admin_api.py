import unittest
from datetime import date

from app.schemas.organization_admin import (
    AssignmentWrite,
    ExternalAssignmentWrite,
    UserAssignmentsReplace,
)


class AssignmentValidationTest(unittest.TestCase):
    def test_allows_multiple_positions_in_same_company(self):
        payload = UserAssignmentsReplace(
            assignments=[
                AssignmentWrite(
                    organization_code="investment",
                    position_code="investment.executive.general_manager",
                    valid_from=date(2026, 1, 1),
                ),
                AssignmentWrite(
                    organization_code="supplymanagement",
                    position_code="governance.supply_leader",
                    valid_from=date(2026, 1, 1),
                ),
            ]
        )
        self.assertEqual(len(payload.assignments), 2)

    def test_external_legal_requires_end_date_and_provider(self):
        with self.assertRaises(ValueError):
            AssignmentWrite(
                organization_code="external.legal",
                position_code="external.legal_counsel",
                valid_from=date(2026, 1, 1),
                external=ExternalAssignmentWrite(
                    provider_name="",
                    service_scopes=[],
                ),
            )

    def test_rejects_end_before_start(self):
        with self.assertRaises(ValueError):
            AssignmentWrite(
                organization_code="supplymanagement",
                position_code="supply.business_handler",
                valid_from=date(2026, 2, 1),
                valid_until=date(2026, 1, 31),
            )
