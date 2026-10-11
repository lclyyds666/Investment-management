import unittest
from pathlib import Path

import app.db.init_db  # noqa: F401
from sqlalchemy import JSON

from app.core.enums import ContractStatus
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.ledger_contract import LedgerContractLink, ScenicContractPreference
from app.schemas.contract import ContractOut


class ContractLedgerLinkModelTest(unittest.TestCase):
    def test_migration_guards_partial_new_tables(self):
        migration = (
            Path(__file__).parents[1]
            / "migrations"
            / "20261010_contract_ledger_invoice_linkage.sql"
        ).read_text(encoding="utf-8")
        guarded_columns = {
            "biz_ledger_contract_link": (
                "id",
                "scenic_id",
                "source_kind",
                "period_key",
                "contract_id",
                "contract_no_snapshot",
                "selected_by",
                "created_at",
                "updated_at",
            ),
            "biz_scenic_contract_preference": (
                "id",
                "scenic_id",
                "source_kind",
                "last_contract_id",
                "created_at",
                "updated_at",
            ),
        }

        for table_name, columns in guarded_columns.items():
            self.assertIn(f"CREATE TABLE IF NOT EXISTS `{table_name}`", migration)
            for column_name in columns:
                self.assertIn(
                    f"table_name='{table_name}' AND column_name='{column_name}'",
                    migration,
                )
        for index_name in (
            "uq_ledger_contract_period",
            "ix_biz_ledger_contract_link_scenic_id",
            "uq_scenic_contract_preference",
            "ix_biz_scenic_contract_preference_scenic_id",
        ):
            self.assertIn(f"index_name='{index_name}'", migration)
        for constraint_name in (
            "fk_ledger_contract_contract",
            "fk_ledger_contract_user",
            "fk_scenic_contract_preference_contract",
        ):
            self.assertIn(f"constraint_name='{constraint_name}'", migration)

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

        contract_scopes = Contract.__table__.c.business_scopes
        self.assertIsInstance(contract_scopes.type, JSON)
        self.assertTrue(contract_scopes.default.is_callable)
        self.assertEqual(contract_scopes.default.arg(None), [])
        self.assertTrue(contract_scopes.nullable)

        approval_contract_fk = next(iter(ApprovalForm.__table__.c.contract_id.foreign_keys))
        invoice_contract_fk = next(iter(Invoice.__table__.c.contract_id.foreign_keys))
        ledger_contract_fk = next(
            iter(LedgerContractLink.__table__.c.contract_id.foreign_keys)
        )
        self.assertTrue(ApprovalForm.__table__.c.contract_id.nullable)
        self.assertTrue(ApprovalForm.__table__.c.scenic_id.nullable)
        self.assertTrue(Invoice.__table__.c.contract_id.nullable)
        self.assertEqual(approval_contract_fk.ondelete, "SET NULL")
        self.assertEqual(invoice_contract_fk.ondelete, "SET NULL")
        self.assertEqual(ledger_contract_fk.ondelete, "RESTRICT")

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
        preference_contract_fk = next(
            iter(ScenicContractPreference.__table__.c.last_contract_id.foreign_keys)
        )
        self.assertEqual(preference_contract_fk.ondelete, "RESTRICT")

    def test_contract_output_normalizes_historical_null_scope_fields(self):
        contract = ContractOut.model_validate(
            {
                "id": 1,
                "contract_no": "HT-1",
                "title": "历史合同",
                "status": ContractStatus.DRAFT,
                "created_by": 1,
                "company_code": "supplymanagement",
                "organization_code": "supplymanagement",
                "contract_term": None,
                "scenic_id": None,
                "business_scopes": None,
            }
        )

        self.assertEqual(contract.contract_term, "")
        self.assertIsNone(contract.scenic_id)
        self.assertEqual(contract.business_scopes, [])


if __name__ == "__main__":
    unittest.main()
