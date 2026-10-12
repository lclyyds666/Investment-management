import unittest
from datetime import date, datetime
from decimal import Decimal

from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger
from app.schemas.financial import FinancialDashboard, ScenicCompletionDetail
from app.services.financial import build_ledger_metrics, build_scenic_completion


def ticket(
    *,
    id=1,
    scenic_id="guanquelou",
    platform="抖音",
    period="P1",
    period_start=None,
    period_end=date(2026, 8, 31),
    created_at=None,
    hexiao="0",
    pending="0",
):
    return TicketLedger(
        id=id,
        scenic_id=scenic_id,
        platform=platform,
        source_file=period,
        period_start=period_start,
        period_end=period_end,
        created_at=created_at,
        hexiao_amount=Decimal(hexiao),
        pending_writeoff=Decimal(pending),
    )


def hotel(**values):
    defaults = {
        "id": 1,
        "scenic_id": "guanquelou",
        "platform": "抖音",
        "source_file": "P1",
        "period_end": date(2026, 8, 31),
        "hexiao_amount": Decimal("0"),
        "pending_writeoff": Decimal("0"),
    }
    aliases = {
        "period": "source_file",
        "hexiao": "hexiao_amount",
        "pending": "pending_writeoff",
    }
    for key, value in values.items():
        defaults[aliases.get(key, key)] = Decimal(value) if key in {"hexiao", "pending"} else value
    return HotelLedger(**defaults)


class ScenicCompletionTest(unittest.TestCase):
    def test_completion_sums_platform_writeoff_but_takes_latest_period_pending_once(self):
        rows = [
            ticket(id=1, platform="抖音", period="P1", period_end=date(2026, 8, 31), hexiao="80", pending="400"),
            ticket(id=2, platform="美团", period="P1", period_end=date(2026, 8, 31), hexiao="20", pending="400"),
            ticket(id=3, platform="抖音", period="P2", period_end=date(2026, 9, 30), hexiao="160", pending="240"),
            ticket(id=4, platform="携程", period="P2", period_end=date(2026, 9, 30), hexiao="40", pending="240"),
        ]
        detail = build_scenic_completion(rows, [])[0]
        self.assertEqual(detail["cumulative_writeoff"], Decimal("300.00"))
        self.assertEqual(detail["pending_writeoff"], Decimal("240.00"))
        self.assertEqual(detail["completion_rate"], Decimal("55.56"))

    def test_zero_denominator_returns_none(self):
        detail = build_scenic_completion(
            [ticket(id=1, scenic_id="empty", period="P1", hexiao="0", pending="0")], []
        )[0]
        self.assertIsNone(detail["completion_rate"])

    def test_ticket_and_hotel_are_independent_for_same_scenic(self):
        details = build_scenic_completion(
            [ticket(scenic_id="quancheng-ouleb", hexiao="80", pending="20")],
            [hotel(scenic_id="quancheng-ouleb", hexiao="60", pending="40")],
        )
        self.assertEqual(
            [(item["business_type"], item["completion_rate"]) for item in details],
            [("hotel", Decimal("60.00")), ("ticket", Decimal("80.00"))],
        )

    def test_dated_period_wins_over_legacy_undated_period(self):
        details = build_scenic_completion([
            ticket(id=99, period="legacy", period_end=None, created_at=datetime(2026, 10, 1), pending="999"),
            ticket(id=1, period="dated", period_end=date(2026, 9, 30), created_at=datetime(2026, 9, 30), pending="100"),
        ], [])
        self.assertEqual(details[0]["pending_writeoff"], Decimal("100.00"))

    def test_undated_periods_fall_back_to_created_at_then_id(self):
        details = build_scenic_completion([
            ticket(id=2, period="old", period_end=None, created_at=datetime(2026, 9, 1), pending="20"),
            ticket(id=1, period="new", period_end=None, created_at=datetime(2026, 10, 1), pending="30"),
        ], [])
        self.assertEqual(details[0]["pending_writeoff"], Decimal("30.00"))

    def test_dashboard_schema_and_metrics_include_completion(self):
        result = build_ledger_metrics([ticket(hexiao="75", pending="25")], [])
        dashboard = FinancialDashboard.model_validate(result)
        self.assertEqual(dashboard.scenic_completion[0].completion_rate, Decimal("75.00"))
        self.assertEqual(
            ScenicCompletionDetail.model_validate(dashboard.scenic_completion[0]).business_type,
            "ticket",
        )


if __name__ == "__main__":
    unittest.main()
