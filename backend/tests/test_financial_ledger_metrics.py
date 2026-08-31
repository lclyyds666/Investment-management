import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock

from app.api.v1.endpoints.operation import router as operation_router
from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger
from app.schemas.financial import FinancialDashboard
from app.services.financial import build_dashboard, build_ledger_metrics


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
        self.assertEqual(result["capital_occupation_days"], 15.4)
        self.assertEqual(result["available_years"], [2026])
        self.assertEqual(result["scenic_ids"], ["quancheng-ouleb", "zunyi-zoo"])
        self.assertNotIn("profit_rate", result)
        self.assertNotIn("available_funds", result)
        self.assertNotIn("projects", result)
        self.assertNotIn("platforms", result)

        hotel_points = [
            point for point in result["ledger_profit"]
            if point["scenic_id"] == "quancheng-ouleb" and point["business_type"] == "hotel"
        ]
        self.assertEqual(len(hotel_points), 1)
        self.assertEqual(hotel_points[0]["service_fee"], Decimal("500"))
        self.assertEqual(hotel_points[0]["realized_amount"], Decimal("2200"))

        ticket_point = next(
            point for point in result["ledger_profit"]
            if point["scenic_id"] == "quancheng-ouleb"
            and point["business_type"] == "ticket"
        )
        self.assertEqual(ticket_point["existing_scale"], Decimal("800"))
        self.assertEqual(ticket_point["occupation_amount"], Decimal("800"))
        self.assertEqual(ticket_point["occupation_weight"], Decimal("8000"))

        hotel_point = hotel_points[0]
        self.assertEqual(hotel_point["existing_scale"], Decimal("1500"))
        self.assertEqual(hotel_point["occupation_amount"], Decimal("1500"))
        self.assertEqual(hotel_point["occupation_weight"], Decimal("30000"))

    def test_cross_month_period_belongs_to_end_month(self):
        tickets = [
            TicketLedger(
                id=6,
                scenic_id="quanzhou-ouleb",
                period_text="2026/1/1-2026/1/20",
                jinying_amount=Decimal("880"),
                service_fee=Decimal("30"),
            ),
            TicketLedger(
                id=5,
                scenic_id="quanzhou-ouleb",
                period_text="2026/4/20-2026/5/19",
                period_start=date(2026, 4, 20),
                period_end=date(2026, 5, 19),
                jinying_amount=Decimal("940"),
                service_fee=Decimal("40"),
            )
        ]

        result = build_ledger_metrics(tickets, [])
        points = {point["period_key"]: point for point in result["ledger_profit"]}
        january_point = points["2026-01"]
        may_point = points["2026-05"]

        self.assertEqual(january_point["month"], 1)
        self.assertEqual(january_point["period"], "1月")
        self.assertEqual(may_point["year"], 2026)
        self.assertEqual(may_point["month"], 5)
        self.assertEqual(may_point["period"], "5月")
        self.assertEqual(may_point["realized_amount"], Decimal("940"))

    def test_dashboard_only_queries_travel_ledgers(self):
        db = Mock()
        db.scalars.side_effect = [Mock(all=Mock(return_value=[])), Mock(all=Mock(return_value=[]))]

        result = build_dashboard(db)

        self.assertEqual(db.scalars.call_count, 2)
        response = FinancialDashboard.model_validate(result).model_dump()
        self.assertEqual(
            set(response),
            {
                "existing_scale",
                "total_realized_scale",
                "total_gross_income",
                "capital_occupation_days",
                "ledger_profit",
                "available_years",
                "scenic_ids",
            },
        )

        point = FinancialDashboard.model_validate({
            **result,
            "ledger_profit": [{
                "scenic_id": "quancheng-ouleb",
                "business_type": "ticket",
                "period": "1月",
                "period_key": "2026-01",
            }],
        }).model_dump()["ledger_profit"][0]
        self.assertEqual(
            set(point),
            {
                "scenic_id",
                "business_type",
                "period",
                "period_key",
                "year",
                "month",
                "service_fee",
                "realized_amount",
                "existing_scale",
                "occupation_weight",
                "occupation_amount",
            },
        )

    def test_independent_data_source_routes_are_removed(self):
        paths = {route.path for route in operation_router.routes}
        self.assertNotIn("/financial/upload", paths)
        self.assertNotIn("/financial/cost", paths)
        self.assertNotIn("/financial/available", paths)
        self.assertNotIn("/projects/upload", paths)


if __name__ == "__main__":
    unittest.main()
