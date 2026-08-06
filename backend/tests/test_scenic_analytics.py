import unittest
from datetime import date, datetime
from decimal import Decimal

from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger
from app.services.scenic_analytics import aggregate_rows, build_financial_metrics


class ScenicAnalyticsTest(unittest.TestCase):
    def test_summary_returns_aggregates_and_partial_coverage_only(self):
        rows = [TicketLedger(
            scenic_id="zunyi-zoo", period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 20), jinying_amount=Decimal("870"),
            service_fee=Decimal("30"), payment_amount=Decimal("1000"),
            co_investment_amount=Decimal("100"), order_count=10, positive_count=8,
            updated_at=datetime(2026, 7, 21, 9, 0), platform="抖音"
        )]
        result = aggregate_rows(rows, [], date(2026, 7, 1), date(2026, 7, 31))[0]
        self.assertEqual(result.sales, Decimal("870"))
        self.assertEqual(result.writeoff_rate, Decimal("80.00"))
        self.assertEqual(result.covered_end.isoformat(), "2026-07-20")
        self.assertTrue(result.partial_coverage)

    def test_date_filter_uses_end_then_start_and_excludes_undated_rows(self):
        rows = [
            TicketLedger(scenic_id="zunyi-zoo", period_start=date(2026, 6, 20),
                         period_end=date(2026, 7, 2), jinying_amount=Decimal("100")),
            TicketLedger(scenic_id="zunyi-zoo", period_start=date(2026, 7, 3),
                         period_end=None, jinying_amount=Decimal("200")),
            TicketLedger(scenic_id="zunyi-zoo", period_start=None, period_end=None,
                         jinying_amount=Decimal("400")),
        ]
        result = aggregate_rows(rows, [], date(2026, 7, 1), date(2026, 7, 31))[0]
        self.assertEqual(result.sales, Decimal("300"))

    def test_hotel_investment_is_counted_once_per_period(self):
        hotels = [
            HotelLedger(id=1, scenic_id="zunyi-zoo", source_file="july.xlsx",
                        period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
                        platform="抖音", payment_amount=Decimal("1000"),
                        co_investment_amount=Decimal("100"), jinying_amount=Decimal("500")),
            HotelLedger(id=2, scenic_id="zunyi-zoo", source_file="july.xlsx",
                        period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
                        platform="美团", payment_amount=Decimal("1000"),
                        co_investment_amount=Decimal("100"), jinying_amount=Decimal("400")),
        ]
        result = aggregate_rows([], hotels, date(2026, 7, 1), date(2026, 7, 31))[0]
        self.assertEqual(result.existing_scale, Decimal("900"))
        self.assertEqual(result.hotel_total, Decimal("900"))

    def test_dashboard_primitives_preserve_undated_rows(self):
        rows = [TicketLedger(scenic_id="zunyi-zoo", jinying_amount=Decimal("50"))]
        result = build_financial_metrics(rows, [])
        self.assertEqual(result["total_realized_scale"], Decimal("50"))
        self.assertEqual(len(result["ledger_profit"]), 1)


if __name__ == "__main__":
    unittest.main()
