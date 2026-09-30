import unittest
from decimal import Decimal
import json
from pathlib import Path

from app.services import hotel_ledger, ticket_ledger


ROOT = Path(__file__).resolve().parents[2]


class ScenicLedgerCalculatorTest(unittest.TestCase):
    def test_changsha_douyin_aggregates_commission_and_rates_for_period(self):
        days = [
            {
                "r": "30000.00", "cs": "30000.10", "cd": "-60.12",
                "ct": "-600.05", "pf": "0",
            },
            {
                "r": "22959.86", "cs": "26991.20", "cd": "-58.13",
                "ct": "-459.05", "pf": "0",
            },
        ]

        result = ticket_ledger.calculate_ticket_ledger(
            "changsha-dongqu",
            days,
            rate_hexiao=Decimal("0.93"),
            rate_settle=Decimal("0.96"),
            commission_rate=Decimal("0.18"),
            platform="抖音",
        )

        self.assertEqual(result["supplier_commission"], Decimal("9081.08"))
        self.assertEqual(result["publisher_due"], Decimal("43878.78"))
        self.assertEqual(result["hexiao_amount"], Decimal("40807.27"))
        self.assertEqual(result["jinying_amount"], Decimal("42123.63"))
        self.assertEqual(result["service_fee"], Decimal("1316.36"))

    def test_changsha_douyin_platform_fee_and_manual_commission_override(self):
        days = [{
            "r": "86", "cs": "100", "cd": "-2", "ct": "-3", "pf": "-4",
        }]
        automatic = ticket_ledger.calculate_ticket_ledger(
            "changsha-dongqu", days,
            rate_hexiao=Decimal("0.93"), rate_settle=Decimal("0.96"),
            commission_rate=Decimal("0.18"), platform="抖音",
        )
        manual = ticket_ledger.calculate_ticket_ledger(
            "changsha-dongqu", days,
            rate_hexiao=Decimal("0.93"), rate_settle=Decimal("0.96"),
            commission_rate=Decimal("0.18"),
            commission_override=Decimal("10.25"), platform="抖音",
        )

        self.assertEqual(automatic["supplier_commission"], Decimal("9.00"))
        self.assertEqual(manual["supplier_commission"], Decimal("10.25"))
        self.assertEqual(manual["publisher_due"], Decimal("75.75"))

    def test_changsha_non_douyin_rounds_period_without_changing_other_scenics(self):
        days = [{"r": "0.01"}, {"r": "0.01"}]
        changsha = ticket_ledger.calculate_ticket_ledger(
            "changsha-dongqu", days,
            rate_hexiao=Decimal("0.50"), rate_settle=Decimal("0.50"),
            platform="携程",
        )
        legacy = ticket_ledger.calculate_ticket_ledger(
            "zunyi-zoo", days,
            rate_hexiao=Decimal("0.50"), rate_settle=Decimal("0.50"),
            platform="携程",
        )

        self.assertEqual(changsha["hexiao_amount"], Decimal("0.01"))
        self.assertEqual(changsha["jinying_amount"], Decimal("0.01"))
        self.assertEqual(legacy["hexiao_amount"], Decimal("0.02"))
        self.assertEqual(legacy["jinying_amount"], Decimal("0.02"))

    def test_guanquelou_daily_snapshot_ignores_stale_commission(self):
        daily = json.dumps([{
            "r": "100", "cs": "8", "cd": "-2", "ct": "1",
        }])
        result = ticket_ledger.calculate_ticket_ledger(
            "guanquelou",
            daily,
            rate_hexiao=Decimal("0.90"),
            rate_settle=Decimal("0.94"),
            commission_override=Decimal("17"),
            commission_rate=Decimal("0.06"),
            platform="抖音",
        )
        self.assertEqual(result["supplier_commission"], Decimal("0.00"))
        self.assertEqual(result["publisher_due"], Decimal("100.00"))
        self.assertEqual(result["hexiao_amount"], Decimal("90.00"))
        self.assertEqual(result["jinying_amount"], Decimal("94.00"))

    def test_guanquelou_no_daily_fallback_ignores_stale_commission(self):
        result = ticket_ledger.calculate_ticket_ledger(
            "guanquelou",
            [],
            supplier_received=Decimal("100"),
            rate_hexiao=Decimal("0.90"),
            rate_settle=Decimal("0.94"),
            commission_override=Decimal("17"),
            platform="抖音",
        )
        self.assertEqual(result["supplier_commission"], Decimal("0.00"))
        self.assertEqual(result["publisher_due"], Decimal("100.00"))
        self.assertEqual(result["hexiao_amount"], Decimal("90.00"))
        self.assertEqual(result["jinying_amount"], Decimal("94.00"))

    def test_quancheng_ticket_excel_uses_common_engine_for_all_scenics(self):
        source = ROOT / "台账" / "对账明细-2026.04.29-2026.05.19.xlsx"
        parsed = ticket_ledger.parse_reconciliation(source.read_bytes(), source.name)
        expected = {
            "supplier_commission": Decimal("267903.31"),
            "publisher_due": Decimal("4814842.21"),
            "hexiao_amount": Decimal("4333358.00"),
            "jinying_amount": Decimal("4525951.68"),
            "service_fee": Decimal("192593.68"),
        }
        scenic_ids = (
            "quancheng-ouleb", "quanzhou-ouleb", "fuzhou-ouleb",
            "zunyi-zoo", "nanyang-wildlife",
        )
        for scenic_id in scenic_ids:
            with self.subTest(scenic_id=scenic_id):
                result = ticket_ledger.calculateTicketLedger(
                    scenic_id,
                    parsed,
                    rate_hexiao=Decimal("0.90"),
                    rate_settle=Decimal("0.94"),
                    commission_rate=Decimal("0.06"),
                )
                self.assertEqual(result["scenic_id"], scenic_id)
                for field, value in expected.items():
                    self.assertEqual(result[field], value)

    def test_quancheng_hotel_excel_uses_common_engine(self):
        source = ROOT / "泉州酒店" / "2026.1.1-1.25明细.xlsx"
        parsed = hotel_ledger.parse_hotel_file(
            source.read_bytes(),
            source.name,
            scenic_id="quancheng-ouleb",
            rate_hexiao=Decimal("0.90"),
            rate_settle=Decimal("0.94"),
            commission_rate=Decimal("0.06"),
        )
        douyin = next(item for item in parsed["platforms"] if item["platform"] == "抖音")
        expected = {
            "supplier_commission": Decimal("9049.97"),
            "settle_base": Decimal("175533.74"),
            "hexiao_amount": Decimal("157980.36"),
            "service_fee": Decimal("7656.00"),
            "jinying_amount": Decimal("165636.36"),
        }
        for scenic_id in ("quancheng-ouleb", "quanzhou-ouleb", "fuzhou-ouleb"):
            with self.subTest(scenic_id=scenic_id):
                result = hotel_ledger.calculateHotelLedger(
                    scenic_id,
                    douyin["daily_json"],
                    platform="抖音",
                    room_nights_override=douyin["room_nights"],
                    rate_hexiao=Decimal("0.90"),
                    rate_settle=Decimal("0.94"),
                    fee_per_night=Decimal("44"),
                    fee_algo=1,
                    commission_rate=Decimal("0.06"),
                )
                self.assertEqual(result["scenic_id"], scenic_id)
                for field, value in expected.items():
                    self.assertEqual(result[field], value)


if __name__ == "__main__":
    unittest.main()
