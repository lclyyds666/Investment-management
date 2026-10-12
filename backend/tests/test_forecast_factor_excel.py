from datetime import date
from decimal import Decimal
from io import BytesIO
import unittest

from openpyxl import Workbook, load_workbook

from app.services.forecast_factor_excel import (
    FACTOR_HEADERS,
    build_factor_template,
    parse_factor_workbook,
)


def workbook_bytes(rows, headers=FACTOR_HEADERS):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


class ForecastFactorExcelTests(unittest.TestCase):
    def test_parser_returns_row_errors_without_dropping_valid_rows(self):
        result = parse_factor_workbook(workbook_bytes([
            ["2026-11-01", "2026-11-03", "changsha", "ticket", "抖音", "天气", "雨天", "-10%", ""],
            [None] * 9,
            ["bad-date", "2026-11-03", "changsha", "ticket", "抖音", "活动", "促销", "5%", ""],
        ]))

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].start_date, date(2026, 11, 1))
        self.assertEqual(result.items[0].impact_rate, Decimal("-0.1"))
        self.assertEqual(result.errors[0].row_no, 4)

    def test_parser_validates_headers_values_dates_and_row_limit(self):
        invalid = parse_factor_workbook(workbook_bytes([
            ["2026-11-04", "2026-11-03", "", "other", "", "其他", "", "201%", "x" * 501],
        ]))
        self.assertEqual(len(invalid.items), 0)
        self.assertEqual(invalid.errors[0].row_no, 2)

        with self.assertRaisesRegex(ValueError, "表头"):
            parse_factor_workbook(workbook_bytes([], headers=["错误表头", *FACTOR_HEADERS[1:]]))

        with self.assertRaisesRegex(ValueError, "1000"):
            parse_factor_workbook(workbook_bytes([
                ["2026-11-01", "2026-11-01", "", "", "", "天气", f"因素{index}", 0, ""]
                for index in range(1001)
            ]))

    def test_template_has_fixed_headers_and_example_row(self):
        sheet = load_workbook(BytesIO(build_factor_template()), data_only=True).active
        self.assertEqual([cell.value for cell in sheet[1]], FACTOR_HEADERS)
        self.assertEqual(sheet.cell(2, 6).value, "天气")


if __name__ == "__main__":
    unittest.main()
