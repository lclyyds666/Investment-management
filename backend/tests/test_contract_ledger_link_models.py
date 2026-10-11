import unittest

import app.db.init_db  # noqa: F401
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.ledger_contract import LedgerContractLink, ScenicContractPreference


class ContractLedgerLinkModelTest(unittest.TestCase):
    def test_period_contract_link_is_unique_per_scenic_kind_and_period(self):
        names = {constraint.name for constraint in LedgerContractLink.__table__.constraints}

        self.assertIn("uq_ledger_contract_period", names)
        self.assertTrue(
            {"contract_term", "scenic_id", "business_scopes"}.issubset(
                Contract.__table__.columns.keys()
            )
        )
        self.assertIn("contract_id", ApprovalForm.__table__.columns)
        self.assertIn("scenic_id", ApprovalForm.__table__.columns)
        self.assertIn("contract_id", Invoice.__table__.columns)

    def test_contract_preference_is_unique_per_scenic_and_source_kind(self):
        names = {
            constraint.name
            for constraint in ScenicContractPreference.__table__.constraints
        }

        self.assertIn("uq_scenic_contract_preference", names)
        self.assertTrue(
            {"scenic_id", "source_kind", "last_contract_id"}.issubset(
                ScenicContractPreference.__table__.columns.keys()
            )
        )


if __name__ == "__main__":
    unittest.main()
