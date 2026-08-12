import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.services.ai_dates import resolve_date_range


class AiDateRangeTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 5, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    def test_last_month_uses_calendar_boundaries(self):
        value = resolve_date_range("上个月", self.now)
        self.assertEqual(value.start.isoformat(), "2026-07-01")
        self.assertEqual(value.end.isoformat(), "2026-07-31")

    def test_recent_three_months_includes_current_partial_month(self):
        value = resolve_date_range("最近三个月", self.now)
        self.assertEqual(value.start.isoformat(), "2026-06-01")
        self.assertEqual(value.end.isoformat(), "2026-08-05")

    def test_named_month_quarter_year_and_explicit_range(self):
        self.assertEqual(
            resolve_date_range("2026年2月", self.now).end.isoformat(), "2026-02-28"
        )
        quarter = resolve_date_range("2025年第4季度", self.now)
        self.assertEqual((quarter.start.isoformat(), quarter.end.isoformat()),
                         ("2025-10-01", "2025-12-31"))
        self.assertEqual(resolve_date_range("2025年", self.now).start.isoformat(), "2025-01-01")
        explicit = resolve_date_range("2026-07-03至2026-07-20", self.now)
        self.assertEqual((explicit.start.isoformat(), explicit.end.isoformat()),
                         ("2026-07-03", "2026-07-20"))

    def test_inverted_and_excessive_ranges_are_rejected(self):
        with self.assertRaises(ValueError):
            resolve_date_range("2026-08-01至2026-07-01", self.now)
        with patch("app.services.ai_dates.settings.AI_MAX_QUERY_MONTHS", 1):
            with self.assertRaises(ValueError):
                resolve_date_range("2026-06-01至2026-07-01", self.now)


if __name__ == "__main__":
    unittest.main()
