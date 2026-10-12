import unittest
from datetime import date, timedelta
from decimal import Decimal

from app.schemas.operation_forecast import ForecastFactor, ForecastRequest
from app.services.operation_forecast import forecast
from app.services.operation_series import OperationDailyPoint


def point(day, settlement, platform="p1", scenic="s1", business="ticket"):
    return OperationDailyPoint(day, scenic, business, platform, Decimal(settlement), Decimal("0"), 0)


def period_points(end_day, totals, platform="p1", scenic="s1"):
    return [
        point(end_day - timedelta(days=index), total, platform=platform, scenic=scenic)
        for index, total in enumerate(totals)
    ]


def request(**changes):
    values = {
        "start_date": date(2026, 7, 1),
        "end_date": date(2026, 7, 1),
        "scenic_ids": ["s1"],
        "business_types": ["ticket"],
        "platforms": ["p1"],
        "factors": [],
    }
    values.update(changes)
    return ForecastRequest(**values)


class OperationForecastTests(unittest.TestCase):
    def test_forecast_normalizes_weights_when_same_period_is_missing(self):
        points = period_points(date(2026, 6, 30), ["30", "24", "18", "12", "6", "3"])
        line = forecast(points, request()).lines[0]

        self.assertEqual(line.components["recent"].weight, Decimal("0.6667"))
        self.assertEqual(line.components["trend"].weight, Decimal("0.3333"))
        self.assertEqual(line.baseline, Decimal("33.64"))

    def test_factor_rates_add_and_are_capped_per_day_with_cent_tail_preserved(self):
        points = period_points(date(2026, 6, 30), ["10.01"] * 12)
        factors = [
            ForecastFactor(start_date=date(2026, 7, 1), end_date=date(2026, 7, 3), factor_type="活动", name="大促", impact_rate=Decimal("1.50")),
            ForecastFactor(start_date=date(2026, 7, 1), end_date=date(2026, 7, 3), scenic_id="s1", platform="p1", factor_type="资讯", name="热搜", impact_rate=Decimal("1.00")),
        ]
        line = forecast(points, request(end_date=date(2026, 7, 3), factors=factors)).lines[0]

        self.assertEqual(line.max_daily_factor, Decimal("2.00"))
        self.assertEqual(line.baseline, Decimal("30.03"))
        self.assertEqual(line.forecast, Decimal("90.09"))
        self.assertEqual(line.factor_adjustment, Decimal("60.06"))

    def test_interval_floor_confidence_and_factor_scope(self):
        points = period_points(date(2026, 6, 30), ["100", "0", "100"])
        factors = [
            ForecastFactor(start_date=date(2026, 7, 1), end_date=date(2026, 7, 1), scenic_id="other", factor_type="天气", name="不适用", impact_rate=Decimal("2")),
            ForecastFactor(start_date=date(2026, 7, 1), end_date=date(2026, 7, 1), factor_type="天气", name="停业", impact_rate=Decimal("-0.80")),
        ]
        line = forecast(points, request(factors=factors)).lines[0]

        self.assertEqual(line.confidence, "medium")
        self.assertEqual(line.max_daily_factor, Decimal("-0.80"))
        self.assertGreaterEqual(line.interval_low, Decimal("0"))
        self.assertGreater(line.interval_high, line.forecast)

    def test_twelve_complete_periods_have_high_confidence(self):
        points = period_points(date(2026, 6, 30), ["10"] * 12)
        line = forecast(points, request()).lines[0]

        self.assertEqual(line.confidence, "high")

    def test_sparse_platform_falls_back_to_business_share_with_low_confidence(self):
        points = period_points(date(2026, 6, 30), ["25"], platform="p1")
        points += period_points(date(2026, 6, 30), ["75", "60", "45", "30", "15", "10"], platform="p2")
        line = forecast(points, request()).lines[0]

        self.assertEqual(line.confidence, "low")
        self.assertIn("same_scenic_business_fallback", line.reasons)
        self.assertIsNotNone(line.forecast)

    def test_unknown_platform_and_missing_business_return_insufficient_data(self):
        points = period_points(date(2026, 6, 30), ["10", "9", "8"], platform="known")
        unknown = forecast(points, request(platforms=["never"])).lines[0]
        missing = forecast(points, request(scenic_ids=["missing"], platforms=["p1"])).lines[0]

        self.assertIsNone(unknown.forecast)
        self.assertIn("insufficient_data", unknown.reasons)
        self.assertIsNone(missing.forecast)
        self.assertIn("insufficient_data", missing.reasons)


if __name__ == "__main__":
    unittest.main()
