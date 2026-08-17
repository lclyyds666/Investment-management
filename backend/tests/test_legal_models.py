import unittest
from pathlib import Path

from app.models.legal_risk import LegalCase, LegalCaseStatus, LegalJudgmentType


class LegalModelContractTest(unittest.TestCase):
    def test_case_statuses_are_fixed(self):
        self.assertEqual(
            [item.value for item in LegalCaseStatus],
            ["review_filing", "in_trial", "judged", "enforcement", "terminal", "closed"],
        )

    def test_judgment_types_include_settlement(self):
        self.assertEqual(
            [item.value for item in LegalJudgmentType],
            ["first_instance", "second_instance", "retrial", "mediation", "settlement"],
        )

    def test_case_has_no_risk_level_or_major_case_field(self):
        columns = set(LegalCase.__table__.columns.keys())
        self.assertNotIn("risk_level", columns)
        self.assertNotIn("major_case", columns)

    def test_mysql_migration_quotes_reserved_row_number_identifier(self):
        source = Path("migrations/20260814_legal_risk_domain.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("`row_number` INT NOT NULL", source)
        self.assertIn("(batch_id, sheet_name, `row_number`)", source)


if __name__ == "__main__":
    unittest.main()
