import unittest
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from app.services.hotel_ledger import parse_hotel_file


RATES = {
    "scenic_id": "quancheng-ouleb",
    "rate_hexiao": Decimal("0.90"),
    "rate_settle": Decimal("0.95"),
    "commission_rate": Decimal("0.06"),
}


class HotelBrandPlatformParserTest(unittest.TestCase):
    @staticmethod
    def _workbook(sheet_titles: list[str]) -> bytes:
        workbook = Workbook()
        workbook.remove(workbook.active)
        for title in sheet_titles:
            worksheet = workbook.create_sheet(title)
            if "美团" in title:
                worksheet.append(["结算金额", "间夜", "入住日期", "离店日期"])
                worksheet.append([100, 1, datetime(2026, 1, 25), datetime(2026, 1, 26)])
            else:
                worksheet.append(["结算价", "间夜", "入住日期", "离店日期"])
                worksheet.append([100, 1, datetime(2026, 1, 25), datetime(2026, 1, 26)])
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    def _branded_workbook(self) -> bytes:
        return self._workbook([
            "海洋携程1.25-2.21", "海洋美团1.25-2.21",
            "骑士携程1.25-2.21", "骑士美团1.25-2.21",
            "长颈鹿携程1.25-2.21", "长颈鹿美团1.25-2.21",
        ])

    def _legacy_workbook(self) -> bytes:
        return self._workbook(["携程1.25-1.31", "携程补充1.25-1.31"])

    def test_three_hotel_brands_are_split_into_six_rows(self):
        parsed = parse_hotel_file(
            self._branded_workbook(), "酒店2026.1.25-2.21.xlsx", **RATES
        )
        self.assertEqual(
            [(row["hotel_name"], row["platform"]) for row in parsed["platforms"]],
            [
                ("海洋", "携程"), ("海洋", "美团"), ("骑士", "携程"),
                ("骑士", "美团"), ("长颈鹿", "携程"), ("长颈鹿", "美团"),
            ],
        )

    def test_unbranded_sheets_still_merge_by_platform(self):
        parsed = parse_hotel_file(
            self._legacy_workbook(), "酒店2026.1.25-1.31.xlsx", **RATES
        )
        self.assertEqual(
            [(row["hotel_name"], row["platform"]) for row in parsed["platforms"]],
            [("", "携程")],
        )

