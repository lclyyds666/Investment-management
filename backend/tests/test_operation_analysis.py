import unittest
from datetime import date
from decimal import Decimal

from app.services.operation_analysis import AnalysisFilters, DateRange, analyze, percentage_change
from app.services.operation_series import OperationDailyPoint


def point(day, settlement, writeoff="0", orders=0, scenic="s1", business="ticket", platform="p1"):
    return OperationDailyPoint(day, scenic, business, platform, Decimal(settlement), Decimal(writeoff), orders)


class OperationAnalysisTests(unittest.TestCase):
    def test_analysis_returns_comparable_previous_and_last_year_periods(self):
        points = [
            point(date(2026, 9, 1), "120.00", "90.00", 12),
            point(date(2026, 8, 2), "100.00", "75.00", 10),
            point(date(2025, 9, 1), "80.00", "60.00", 8),
        ]
        result = analyze(points, DateRange(date(2026, 9, 1), date(2026, 9, 30)), AnalysisFilters())
        self.assertEqual(result.summary.settlement_amount, Decimal("120.00"))
        self.assertEqual(result.comparisons.settlement.mom_rate, Decimal("20.00"))
        self.assertEqual(result.comparisons.settlement.yoy_rate, Decimal("50.00"))
        self.assertEqual(len(result.trends), 30)

    def test_zero_comparison_denominator_returns_none(self):
        result = analyze(
            [point(date(2026, 9, 1), "10", orders=2)],
            DateRange(date(2026, 9, 1), date(2026, 9, 1)),
            AnalysisFilters(),
        )
        self.assertIsNone(result.comparisons.orders.mom_rate)
        self.assertIsNone(percentage_change(Decimal("1"), Decimal("0")))

    def test_filters_rankings_contributions_and_anomalies_are_explainable(self):
        points = [
            point(date(2026, 9, 1), "200", scenic="keep"),
            point(date(2026, 8, 31), "100", scenic="keep"),
            point(date(2026, 9, 1), "999", scenic="drop"),
        ]
        result = analyze(
            points,
            DateRange(date(2026, 9, 1), date(2026, 9, 1)),
            AnalysisFilters(scenic_ids=["keep"]),
        )
        self.assertEqual(result.summary.settlement_amount, Decimal("200.00"))
        self.assertTrue(any(item.dimension == "scenic_id" and item.value == "keep" for item in result.rankings))
        scenic_contribution = next(item for item in result.contributions if item.dimension == "scenic_id")
        self.assertEqual(scenic_contribution.settlement_change, Decimal("100.00"))
        self.assertEqual(scenic_contribution.contribution_rate, Decimal("50.00"))
        self.assertEqual(result.anomalies[0].rule, "mom_change")
        self.assertEqual(result.anomalies[0].evidence, Decimal("100.00"))

    def test_sparse_history_does_not_trigger_standard_deviation_rule(self):
        result = analyze(
            [point(date(2026, 9, 1), "100"), point(date(2026, 8, 31), "10")],
            DateRange(date(2026, 9, 1), date(2026, 9, 1)),
            AnalysisFilters(),
        )
        self.assertFalse(any(item.rule == "standard_deviation" for item in result.anomalies))

    def test_divergence_and_platform_share_shift_have_reasons(self):
        points = [point(date(2026, 9, 1), "180", orders=4, platform="a"),
                  point(date(2026, 9, 1), "20", orders=1, platform="b"),
                  point(date(2026, 8, 31), "20", orders=2, platform="a"),
                  point(date(2026, 8, 31), "80", orders=8, platform="b")]
        result = analyze(points, DateRange(date(2026, 9, 1), date(2026, 9, 1)), AnalysisFilters())
        self.assertIn("amount_order_divergence", [item.rule for item in result.anomalies])
        shifts = [item for item in result.anomalies if item.rule == "platform_concentration"]
        self.assertEqual([item.dimension for item in shifts], ["a", "b"])
        self.assertTrue(all(item.reason and item.suggestion for item in result.anomalies))


if __name__ == "__main__":
    unittest.main()
