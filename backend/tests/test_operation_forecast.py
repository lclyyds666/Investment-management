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
    def test_tiny_calendar_baseline_is_preserved_without_negative_daily_tail(self):
        from app.services.operation_forecast import _allocate_daily
        start = date(2026, 7, 1)
        points = [point(start-timedelta(days=i+1), "0.01" if (i % 7 + i // 7) % 7 < 4 else "0") for i in range(84)]
        line = forecast(points, request(end_date=start+timedelta(days=6))).lines[0]
        self.assertEqual(line.baseline, Decimal("0.04"))
        self.assertEqual(line.forecast, line.baseline)
        self.assertEqual(line.factor_adjustment, 0)
        self.assertEqual(line.factor_contributions, [])
        allocated = _allocate_daily(Decimal("0.04"), [Decimal(1)] * 7)
        self.assertEqual(sum(allocated), Decimal("0.04"))
        self.assertTrue(all(value >= 0 for value in allocated))

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

        self.assertEqual(line.confidence, "low")
        self.assertTrue(any("missing_history_dates" in reason for reason in line.reasons))
        self.assertEqual(line.max_daily_factor, Decimal("-0.80"))
        self.assertGreaterEqual(line.interval_low, Decimal("0"))
        self.assertGreater(line.interval_high, line.forecast)

    def test_twelve_complete_periods_have_high_confidence(self):
        points = period_points(date(2026, 6, 30), ["10"] * 12)
        line = forecast(points, request()).lines[0]

        self.assertEqual(line.confidence, "high")

    def test_calendar_weekdays_are_learned_and_holidays_are_not_invented(self):
        start = date(2026, 7, 1)
        points = [point(start - timedelta(days=i), "30" if (start-timedelta(days=i)).weekday() >= 5 else "10") for i in range(-2, 85)]
        weekday = forecast(points, request()).lines[0]
        weekend = forecast(points, request(start_date=date(2026, 7, 4), end_date=date(2026, 7, 4))).lines[0]
        self.assertTrue(weekday.calendar["weekday_applied"])
        self.assertGreater(Decimal(weekend.calendar["weekday_factor"]), Decimal(weekday.calendar["weekday_factor"]))
        self.assertIsNone(weekday.calendar["statutory_holiday_source"])
        self.assertTrue(any("statutory_calendar_unavailable" in reason for reason in weekday.reasons))

    def test_signed_clamp_contributions_reconcile_all_metrics_and_order_rounding(self):
        points = [OperationDailyPoint(date(2026, 6, 30)-timedelta(days=i), "s1", "ticket", "p1", Decimal("10.01"), Decimal("6.33"), 3) for i in range(12)]
        factors = [ForecastFactor(start_date=date(2026, 7, 1), end_date=date(2026, 7, 1), factor_type="活动", name=str(i), impact_rate=rate) for i, rate in enumerate(["2", "1", "-0.5"])]
        factors.append(ForecastFactor(start_date=date(2026, 7, 2), end_date=date(2026, 7, 2), factor_type="节假日", name="outside", impact_rate="1"))
        lines = forecast(points, request(factors=factors), all_metrics=True).lines
        self.assertEqual(len(lines), 3)
        for line in lines:
            values = [Decimal(item["contribution"]) for item in line.factor_contributions]
            self.assertEqual(sum(values), line.forecast-line.baseline)
            self.assertLess(values[2], 0)
            self.assertEqual(values[3], 0)
            self.assertEqual(line.max_daily_factor, Decimal(2))
            if line.metric == "order_count":
                self.assertTrue(all(value == value.to_integral_value() for value in values))

    def test_volatile_complete_history_downgrades_confidence(self):
        line = forecast(period_points(date(2026, 6, 30), ["1", "100"] * 6), request()).lines[0]
        self.assertEqual(line.confidence, "low")
        self.assertTrue(any("high_history_volatility" in reason for reason in line.reasons))

    def test_sparse_platform_falls_back_to_business_share_with_low_confidence(self):
        points = period_points(date(2026, 6, 30), ["25"], platform="p1")
        points += period_points(date(2026, 6, 30), ["75", "60", "45", "30", "15", "10"], platform="p2")
        line = forecast(points, request()).lines[0]

        self.assertEqual(line.confidence, "low")
        self.assertIn("same_scenic_business_fallback", line.reasons)
        self.assertIsNotNone(line.forecast)

    def test_fallback_share_does_not_use_future_points(self):
        points = period_points(date(2026, 6, 30), ["25"], platform="p1")
        points += period_points(date(2026, 6, 30), ["75", "60", "45"], platform="p2")
        baseline = forecast(points, request()).lines[0].baseline
        points.append(point(date(2026, 7, 2), "900", platform="p1"))
        line = forecast(points, request()).lines[0]

        self.assertEqual(line.baseline, baseline)

    def test_unfiltered_request_only_returns_observed_dimension_combinations(self):
        points = period_points(date(2026, 6, 30), ["10", "9", "8"], platform="p1", scenic="s1")
        points += [
            point(date(2026, 6, 30) - timedelta(days=index), total, platform="p2", scenic="s2", business="hotel")
            for index, total in enumerate(["20", "18", "16"])
        ]
        unfiltered = request(scenic_ids=[], business_types=[], platforms=[])

        keys = {
            (line.scenic_id, line.business_type, line.platform)
            for line in forecast(points, unfiltered).lines
        }
        self.assertEqual(keys, {("s1", "ticket", "p1"), ("s2", "hotel", "p2")})

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
