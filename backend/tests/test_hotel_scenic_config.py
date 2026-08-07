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

from app.api.v1.endpoints import hotel_ledger as hotel_endpoint
from app.schemas.hotel_ledger import HotelSaveIn, HotelSaveRow
from app.services import hotel_ledger


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _SaveSession:
    def __init__(self):
        self.rows = []

    def scalar(self, _statement):
        return 0

    def scalars(self, _statement):
        return _Rows(self.rows)

    def add(self, row):
        row.id = len(self.rows) + 1
        row.pending_writeoff = Decimal("0")
        row.confirm_stored = ""
        row.confirm_name = ""
        row.confirmed = False
        row.created_at = datetime(2026, 8, 1)
        self.rows.append(row)

    def flush(self):
        return None

    def commit(self):
        return None


class HotelScenicConfigTest(unittest.TestCase):
    @staticmethod
    def _douyin_workbook() -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "抖音明细8.1-8.1"
        ws.append([
            "订单实收金额",
            "软件服务费",
            "团长服务费",
            "达人服务费",
            "服务商服务费",
            "间夜",
            "核销时间",
        ])
        ws.append([100, -4, -3, -2, -91, 1, datetime(2026, 8, 1, 12, 0)])
        output = BytesIO()
        wb.save(output)
        wb.close()
        return output.getvalue()

    def test_parser_uses_explicit_scenic_rate_snapshot(self):
        parsed = hotel_ledger.parse_hotel_file(
            self._douyin_workbook(),
            "福州欧乐堡8.1-8.1.xlsx",
            scenic_id="fuzhou-ouleb",
            rate_hexiao=Decimal("0.91"),
            rate_settle=Decimal("0.95"),
            commission_rate=Decimal("0.08"),
        )

        douyin = parsed["platforms"][0]
        self.assertEqual(douyin["base_received"], Decimal("91.00"))
        self.assertEqual(douyin["suggested_commission"], Decimal("3.00"))
        self.assertEqual(douyin["def_hexiao"], Decimal("80.08"))
        self.assertEqual(douyin["rate_hexiao"], Decimal("0.91"))
        self.assertEqual(douyin["rate_settle"], Decimal("0.95"))
        self.assertEqual(douyin["commission_rate"], Decimal("0.08"))

    def test_parse_endpoint_reads_persisted_scenic_config(self):
        config = SimpleNamespace(
            scenic_id="fuzhou-ouleb",
            scenic_name="福州欧乐堡",
            sort_order=30,
            default_ticket_product="水上世界/童话世界/海洋王国",
            ticket_rate_hexiao=Decimal("0.91"),
            ticket_rate_settle=Decimal("0.95"),
            ticket_commission_rate=Decimal("0.08"),
            ticket_default_commission=None,
            updated_by=1,
            updated_at=None,
        )
        db = SimpleNamespace(get=lambda _model, _scenic_id: config)
        upload = UploadFile(
            filename="福州欧乐堡8.1-8.1.xlsx",
            file=BytesIO(self._douyin_workbook()),
        )

        with TemporaryDirectory() as temp_dir:
            with patch.object(hotel_endpoint, "_detail_dir", return_value=Path(temp_dir)):
                response = asyncio.run(hotel_endpoint.parse_file(
                    scenic_id="fuzhou-ouleb",
                    files=[upload],
                    db=db,
                    _=None,
                ))

        douyin = response.data.platforms[0]
        self.assertEqual(douyin.suggested_commission, Decimal("3.00"))
        self.assertEqual(douyin.def_hexiao, Decimal("80.08"))
        self.assertEqual(douyin.rate_hexiao, Decimal("0.91"))
        self.assertEqual(douyin.rate_settle, Decimal("0.95"))
        self.assertEqual(douyin.commission_rate, Decimal("0.08"))

    @staticmethod
    def _fuzhou_config():
        return SimpleNamespace(
            ticket_rate_hexiao=Decimal("0.91"),
            ticket_rate_settle=Decimal("0.95"),
            ticket_commission_rate=Decimal("0.08"),
        )

    def test_save_uses_current_scenic_config_when_legacy_client_omits_rates(self):
        session = _SaveSession()
        payload = HotelSaveIn(rows=[HotelSaveRow(
            platform="抖音",
            hotel_name="测试酒店",
            base_received=Decimal("100"),
        )])

        with patch.object(
            hotel_endpoint,
            "get_effective_config",
            return_value=self._fuzhou_config(),
        ):
            hotel_endpoint.save_ledger(
                "fuzhou-ouleb",
                payload,
                session,
                SimpleNamespace(id=9),
            )

        saved = session.rows[0]
        self.assertEqual(saved.rate_hexiao, Decimal("0.91"))
        self.assertEqual(saved.rate_settle, Decimal("0.95"))
        self.assertEqual(saved.commission_rate, Decimal("0.08"))

    def test_save_preserves_explicit_historical_rate_snapshot(self):
        session = _SaveSession()
        payload = HotelSaveIn(rows=[HotelSaveRow(
            platform="抖音",
            hotel_name="测试酒店",
            base_received=Decimal("100"),
            rate_hexiao=Decimal("0.80"),
            rate_settle=Decimal("0.85"),
            commission_rate=Decimal("0"),
        )])

        with patch.object(
            hotel_endpoint,
            "get_effective_config",
            return_value=self._fuzhou_config(),
        ):
            hotel_endpoint.save_ledger(
                "fuzhou-ouleb",
                payload,
                session,
                SimpleNamespace(id=9),
            )

        saved = session.rows[0]
        self.assertEqual(saved.rate_hexiao, Decimal("0.80"))
        self.assertEqual(saved.rate_settle, Decimal("0.85"))
        self.assertEqual(saved.commission_rate, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
