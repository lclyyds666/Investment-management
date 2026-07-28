import unittest
from decimal import Decimal
from pathlib import Path

from app.services import hotel_ledger, ticket_ledger


ROOT = Path(__file__).resolve().parents[2]


class ScenicLedgerCalculatorTest(unittest.TestCase):
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
        parsed = hotel_ledger.parse_hotel_file(source.read_bytes(), source.name)
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
