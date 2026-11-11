import unittest
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.services.operation_series import build_confirmed_daily_series


@dataclass
class Row:
    period_start: date | None = None
    period_end: date | None = None
    jinying_amount: Decimal = Decimal("0")
    hexiao_amount: Decimal = Decimal("0")
    order_count: int = 0
    confirmed: bool = True
    id: int = 1
    scenic_id: str = "scenic"
    platform: str = "platform"


class OperationSeriesTests(unittest.TestCase):
    def test_tiny_signed_amounts_preserve_cents_and_partial_day_analysis(self):
        from app.services.operation_analysis import AnalysisFilters, DateRange, analyze
        for sign in (Decimal(1), Decimal(-1)):
            for business in ("ticket", "hotel"):
                row = Row(period_start=date(2026, 10, 1), period_end=date(2026, 10, 4),
                          jinying_amount=sign * Decimal("0.02"), hexiao_amount=sign * Decimal("0.01"))
                points, issues = build_confirmed_daily_series([row] if business == "ticket" else [],
                                                             [row] if business == "hotel" else [])
                self.assertEqual(issues, [])
                self.assertEqual(sum(p.settlement_amount for p in points), row.jinying_amount)
                self.assertEqual(sum(p.writeoff_amount for p in points), row.hexiao_amount)
                for offset in range(4):
                    day = row.period_start + timedelta(days=offset)
                    result = analyze(points, DateRange(day, day), AnalysisFilters())
                    self.assertGreaterEqual(result.summary.settlement_amount * sign, 0)
                    self.assertGreaterEqual(result.summary.writeoff_amount * sign, 0)
                    self.assertLessEqual(abs(result.summary.settlement_amount), abs(row.jinying_amount))

    def test_confirmed_three_day_period_is_split_without_losing_totals(self):
        points, issues = build_confirmed_daily_series([Row(
            period_start=date(2026, 10, 1), period_end=date(2026, 10, 3),
            jinying_amount=Decimal("100.00"), hexiao_amount=Decimal("80.00"), order_count=10,
        )], [])
        self.assertEqual(len(points), 3)
        self.assertEqual(sum(p.settlement_amount for p in points), Decimal("100.00"))
        self.assertEqual(sum(p.writeoff_amount for p in points), Decimal("80.00"))
        self.assertEqual(sum(p.order_count for p in points), 10)
        self.assertEqual(issues, [])

    def test_unconfirmed_and_undated_rows_are_excluded(self):
        points, issues = build_confirmed_daily_series(
            [Row(confirmed=False), Row(period_start=None, period_end=None, id=9)], []
        )
        self.assertEqual(len(points), 0)
        self.assertEqual(issues[0].code, "missing_period_dates")

    def test_invalid_period_is_reported(self):
        points, issues = build_confirmed_daily_series(
            [Row(period_start=date(2026, 10, 3), period_end=date(2026, 10, 1))], []
        )
        self.assertEqual(points, [])
        self.assertEqual(issues[0].code, "missing_period_dates")


if __name__ == "__main__":
    unittest.main()
