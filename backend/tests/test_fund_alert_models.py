import unittest
from pathlib import Path

from app.db.base import Base
from app.models.fund_alert import FundAlertReceipt


class FundAlertReceiptModelTest(unittest.TestCase):
    def test_daily_stage_receipt_has_expected_unique_key_and_cascades(self):
        constraint = next(
            item
            for item in FundAlertReceipt.__table__.constraints
            if item.name == "uq_fund_alert_receipt_daily_stage"
        )
        self.assertEqual(
            [column.name for column in constraint.columns],
            ["user_id", "fund_id", "alert_date", "stage"],
        )
        foreign_keys = {
            foreign_key.parent.name: (foreign_key.target_fullname, foreign_key.ondelete)
            for foreign_key in FundAlertReceipt.__table__.foreign_keys
        }
        self.assertEqual(
            foreign_keys["fund_id"],
            ("biz_fund_transaction.id", "CASCADE"),
        )
        self.assertEqual(foreign_keys["user_id"], ("sys_user.id", "CASCADE"))

    def test_model_columns_and_lookup_index_match_contract(self):
        self.assertEqual(FundAlertReceipt.__tablename__, "biz_fund_alert_receipt")
        self.assertIn("biz_fund_alert_receipt", Base.metadata.tables)
        self.assertEqual(
            set(FundAlertReceipt.__table__.columns.keys()),
            {
                "id",
                "user_id",
                "fund_id",
                "alert_date",
                "stage",
                "shown_at",
                "created_at",
                "updated_at",
            },
        )
        lookup = next(
            index
            for index in FundAlertReceipt.__table__.indexes
            if index.name == "ix_fund_alert_receipt_lookup"
        )
        self.assertEqual(
            [column.name for column in lookup.columns],
            ["user_id", "alert_date", "stage"],
        )

    def test_mysql_migration_is_repeatable_and_matches_model(self):
        migration = (
            Path(__file__).parents[1]
            / "migrations"
            / "20261010_fund_alert_receipts.sql"
        )
        source = migration.read_text(encoding="utf-8")
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS `biz_fund_alert_receipt`",
            source,
        )
        self.assertIn(
            "UNIQUE KEY `uq_fund_alert_receipt_daily_stage`",
            source,
        )
        self.assertIn(
            "FOREIGN KEY (`fund_id`) REFERENCES `biz_fund_transaction` (`id`) ON DELETE CASCADE",
            source,
        )
        self.assertIn(
            "FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE",
            source,
        )

    def test_registration_modules_export_receipt_model(self):
        from app import models
        from app.db import init_db

        self.assertIs(models.FundAlertReceipt, FundAlertReceipt)
        self.assertIs(init_db.FundAlertReceipt, FundAlertReceipt)


if __name__ == "__main__":
    unittest.main()
