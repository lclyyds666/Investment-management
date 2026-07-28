import unittest
from datetime import date
from decimal import Decimal

from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger
from app.services.financial import build_ledger_metrics


class FinancialLedgerMetricsTest(unittest.TestCase):
    def test_metrics_use_ledger_snapshots_and_deduplicate_hotel_period(self):
        tickets = [
            TicketLedger(
                id=1,
                scenic_id="quancheng-ouleb",
                period_text="2026-01期",
                period_start=date(2026, 1, 1),
                payment_amount=Decimal("1000"),
                co_investment_amount=Decimal("200"),
                jinying_amount=Decimal("900"),
                service_fee=Decimal("100"),
                pay_date=date(2026, 1, 1),
                repay_date=date(2026, 1, 11),
                repay_amount=Decimal("800"),
            ),
            TicketLedger(
                id=2,
                scenic_id="zunyi-zoo",
                period_text="2026-03期",
                period_start=date(2026, 3, 1),
                payment_amount=Decimal("500"),
                co_investment_amount=Decimal("0"),
                jinying_amount=Decimal("400"),
                service_fee=Decimal("50"),
                pay_date=date(2026, 3, 1),
                repay_date=None,
                repay_amount=None,
            ),
        ]
        hotels = [
            HotelLedger(
                id=3,
                scenic_id="quancheng-ouleb",
                source_file="hotel-2026-02.xlsx",
                period_text="2026-02期",
                period_start=date(2026, 2, 1),
                platform="抖音",
                payment_amount=Decimal("2000"),
                co_investment_amount=Decimal("500"),
                jinying_amount=Decimal("1000"),
                service_fee=Decimal("200"),
                payment_date=date(2026, 2, 1),
                repay_date=date(2026, 2, 21),
                repay_amount=Decimal("1500"),
            ),
            HotelLedger(
                id=4,
                scenic_id="quancheng-ouleb",
                source_file="hotel-2026-02.xlsx",
                period_text="2026-02期",
                period_start=date(2026, 2, 1),
                platform="美团",
                payment_amount=Decimal("2000"),
                co_investment_amount=Decimal("500"),
                jinying_amount=Decimal("1200"),
                service_fee=Decimal("300"),
                payment_date=date(2026, 2, 1),
                repay_date=date(2026, 2, 21),
                repay_amount=Decimal("1500"),
            ),
        ]

        result = build_ledger_metrics(tickets, hotels, today=date(2026, 3, 11))

        self.assertEqual(result["existing_scale"], Decimal("2800"))
        self.assertEqual(result["total_realized_scale"], Decimal("3500"))
        self.assertEqual(result["total_gross_income"], Decimal("650"))
        self.assertEqual(result["profit_rate"], 23.21)
        self.assertEqual(result["capital_occupation_days"], 15.4)
        self.assertEqual(result["available_years"], [2026])
        self.assertEqual(result["scenic_ids"], ["quancheng-ouleb", "zunyi-zoo"])

        hotel_points = [
            point for point in result["ledger_profit"]
            if point["scenic_id"] == "quancheng-ouleb" and point["business_type"] == "hotel"
        ]
        self.assertEqual(len(hotel_points), 1)
        self.assertEqual(hotel_points[0]["service_fee"], Decimal("500"))


if __name__ == "__main__":
    unittest.main()
