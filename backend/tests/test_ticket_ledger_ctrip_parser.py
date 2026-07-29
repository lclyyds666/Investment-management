import asyncio
import unittest
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import UploadFile
from openpyxl import Workbook

from app.api.v1.endpoints import ticket_ledger as ticket_endpoint
from app.services import ticket_ledger


class TicketLedgerCtripParserTest(unittest.TestCase):
    @staticmethod
    def _workbook_bytes() -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "抖音明细7.3-7.12"
        ws.append(["订单实收金额", "软件服务费", "达人服务费", "团长服务费", "核销时间"])
        ws.append([100, -1, -2, -3, datetime(2026, 7, 3, 10, 0)])

        headers = ["结算价金额", "流水类型", "服务完成日期", "出发时间", "付款日期"]
        ctrip_sheets = (
            ("携程明细7.3-7.12", [77] * 9 + [81], datetime(2026, 7, 3)),
            ("携程明细7.13-7.19", [62] * 15 + [75], datetime(2026, 7, 13)),
            ("携程明细7.20-7.26", [66] * 16 + [68], datetime(2026, 7, 26)),
        )
        for title, amounts, departure in ctrip_sheets:
            sheet = wb.create_sheet(title)
            sheet.append(headers)
            for amount in amounts:
                # 真实文件的服务完成日期为空，应回退到出发时间。
                sheet.append([amount, "订单成本", None, departure, datetime(2026, 7, 1)])
        # 非订单成本流水不得进入门票核销金额。
        wb["携程明细7.20-7.26"].append(
            [999, "调账", None, datetime(2026, 7, 26), datetime(2026, 7, 1)]
        )

        output = BytesIO()
        wb.save(output)
        wb.close()
        return output.getvalue()

    def test_mixed_file_is_split_by_platform_and_ctrip_is_calculated(self):
        parsed = ticket_ledger.parse_reconciliation(
            self._workbook_bytes(), "对账明细-2026.07.03-2026.07.25.xlsx"
        )
        self.assertEqual([item["platform"] for item in parsed["platforms"]], ["抖音", "携程"])

        douyin = parsed["platforms"][0]
        self.assertEqual(douyin["supplier_received"], Decimal("94.00"))
        self.assertEqual(douyin["suggested_commission"], Decimal("1.00"))

        ctrip = parsed["platforms"][1]
        self.assertEqual(ctrip["supplier_received"], Decimal("2903.00"))
        self.assertEqual(ctrip["suggested_commission"], Decimal("0.00"))
        self.assertEqual(ctrip["order_count"], 43)
        self.assertEqual(ctrip["positive_count"], 43)
        self.assertEqual(ctrip["period_start"].isoformat(), "2026-07-03")
        # 台账期次仍以文件名为准，7月26日明细只参与金额计算。
        self.assertEqual(ctrip["period_end"].isoformat(), "2026-07-25")
        self.assertTrue(ctrip["daily_json"])

        calculated = ticket_ledger.recompute_from_json(
            ctrip["daily_json"],
            Decimal("0.90"),
            Decimal("0.94"),
            ctrip["suggested_commission"],
            platform="携程",
            scenic_id="test-scenic",
        )
        self.assertEqual(calculated["publisher_due"], Decimal("2903.00"))
        self.assertEqual(calculated["hexiao_amount"], Decimal("2612.70"))
        self.assertEqual(calculated["jinying_amount"], Decimal("2728.82"))
        self.assertEqual(calculated["service_fee"], Decimal("116.12"))

    def test_running_balance_groups_platform_rows_as_one_period(self):
        rows = [
            SimpleNamespace(source_file="period-1.xlsx", payment_amount=5000, hexiao_amount=100),
            SimpleNamespace(source_file="period-1.xlsx", payment_amount=5000, hexiao_amount=200),
            SimpleNamespace(source_file="period-2.xlsx", payment_amount=0, hexiao_amount=50),
        ]
        balances = ticket_ledger.calculate_running_balances(
            "test-scenic", rows, group_by=lambda row: row.source_file
        )
        self.assertEqual(
            balances,
            [Decimal("4700.00"), Decimal("4700.00"), Decimal("4650.00")],
        )

    def test_parse_api_returns_one_draft_per_platform(self):
        upload = UploadFile(
            filename="对账明细-2026.07.03-2026.07.25.xlsx",
            file=BytesIO(self._workbook_bytes()),
        )
        with TemporaryDirectory() as temp_dir:
            with patch.object(ticket_endpoint, "_detail_dir", return_value=Path(temp_dir)):
                response = asyncio.run(
                    ticket_endpoint.parse_files(
                        scenic_id="test-scenic", files=[upload], db=None, _=None
                    )
                )
        self.assertEqual(response.code, 0)
        self.assertEqual(response.data.succeeded, 2)
        self.assertEqual(
            [item.platform for item in response.data.files], ["抖音", "携程"]
        )
        self.assertEqual(response.data.files[1].supplier_received, Decimal("2903.00"))
        self.assertTrue(response.data.files[1].daily_json)


if __name__ == "__main__":
    unittest.main()
