import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

from app.schemas.fund import FundTransactionCreate
from app.services.fund import maturity_state, summarize_funds


class FundManagementTest(unittest.TestCase):
    def test_summary_and_warning_boundaries(self):
        rows = [
            SimpleNamespace(
                direction="increase", category="bank_credit",
                amount=Decimal("1000000"), maturity_date=date(2026, 9, 27),
                settlement_status="open",
            ),
            SimpleNamespace(
                direction="increase", category="customer_payment",
                amount=Decimal("200000"), maturity_date=None,
                settlement_status="open",
            ),
            SimpleNamespace(
                direction="usage", category="business_payment",
                amount=Decimal("350000"), maturity_date=None,
                settlement_status="open",
            ),
        ]

        summary = summarize_funds(rows, today=date(2026, 8, 28))

        self.assertEqual(summary.total_increase, Decimal("1200000"))
        self.assertEqual(summary.total_usage, Decimal("350000"))
        self.assertEqual(summary.available_funds, Decimal("850000"))
        self.assertEqual(summary.due_within_30_amount, Decimal("1000000"))
        self.assertEqual(maturity_state(rows[0], date(2026, 8, 28)), "due_soon")

    def test_day_31_is_not_due_soon_and_past_date_is_overdue(self):
        day_31 = SimpleNamespace(
            direction="increase", category="company_loan",
            maturity_date=date(2026, 9, 28), settlement_status="open",
        )
        overdue = SimpleNamespace(
            direction="increase", category="company_loan",
            maturity_date=date(2026, 8, 27), settlement_status="open",
        )
        self.assertEqual(maturity_state(day_31, date(2026, 8, 28)), "normal")
        self.assertEqual(maturity_state(overdue, date(2026, 8, 28)), "overdue")

    def test_credit_requires_maturity_and_positive_amount(self):
        with self.assertRaises(ValidationError):
            FundTransactionCreate(
                direction="increase", category="bank_credit",
                amount=Decimal("1"), occurred_on=date(2026, 8, 28),
                counterparty="test bank", summary="working capital credit",
            )
        with self.assertRaises(ValidationError):
            FundTransactionCreate(
                direction="usage", category="customer_payment",
                amount=Decimal("0"), occurred_on=date(2026, 8, 28),
                counterparty="customer", summary="invalid direction category pair",
            )

    def test_amount_rejects_values_beyond_database_precision(self):
        payload = {
            "direction": "usage",
            "category": "business_payment",
            "occurred_on": date(2026, 8, 28),
        }
        for amount in (Decimal("99999999999999999.99"), Decimal("1.001")):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                FundTransactionCreate(amount=amount, **payload)

    def test_migration_ids_match_repository_integer_primary_keys(self):
        migration = Path(__file__).parents[1] / "migrations" / "20260828_fund_management.sql"
        sql = migration.read_text(encoding="utf-8")

        self.assertIn("`id` INT NOT NULL AUTO_INCREMENT", sql)
        self.assertIn("`created_by` INT NULL", sql)
        self.assertNotIn("`created_by` BIGINT", sql)


if __name__ == "__main__":
    unittest.main()
