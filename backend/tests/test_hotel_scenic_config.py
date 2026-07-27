from __future__ import annotations

import asyncio
import io
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import UploadFile
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints import hotel_ledger as hotel_api
from app.db.base import Base
from app.models.hotel_ledger import HotelLedger
from app.models.scenic_config import ScenicConfig
from app.models.user import User
from app.schemas.hotel_ledger import HotelSaveIn
from app.services import hotel_ledger as hotel_service


REPO_ROOT = Path(__file__).resolve().parents[2]
HOTEL_EXCEL = REPO_ROOT / "泉州酒店" / "2026.1.1-1.25明细.xlsx"


class HotelScenicConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, ScenicConfig.__table__, HotelLedger.__table__],
        )
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _add_config(self, scenic_id: str) -> ScenicConfig:
        config = ScenicConfig(
            scenic_id=scenic_id,
            scenic_name="酒店配置测试景区",
            rate_hexiao=Decimal("0.9000"),
            rate_settle=Decimal("0.9100"),
            commission_rate=Decimal("0.0600"),
            hotel_fee_algo=1,
            fee_per_night=Decimal("30.00"),
            enabled=True,
        )
        self.db.add(config)
        self.db.commit()
        return config

    def _save(self, scenic_id: str, **row_values) -> HotelLedger:
        values = {
            "platform": "美团",
            "base_received": Decimal("100.00"),
            "room_nights": 2,
        }
        values.update(row_values)
        hotel_api.save_ledger(
            scenic_id,
            HotelSaveIn(rows=[values], mode="append"),
            db=self.db,
            current_user=SimpleNamespace(id=1),
        )
        return self.db.scalar(
            select(HotelLedger)
            .where(HotelLedger.scenic_id == scenic_id)
            .order_by(HotelLedger.id.desc())
        )

    def test_excel_parse_save_and_snapshot_use_scenic_config(self) -> None:
        scenic_id = "hotel-config-test"
        config = self._add_config(scenic_id)

        with TemporaryDirectory() as temp_dir, HOTEL_EXCEL.open("rb") as stream:
            with patch.object(
                hotel_api,
                "_detail_dir",
                return_value=Path(temp_dir) / scenic_id,
            ):
                response = asyncio.run(hotel_api.parse_file(
                    scenic_id,
                    [UploadFile(filename=HOTEL_EXCEL.name, file=stream)],
                    rate_hexiao=None,
                    rate_settle=None,
                    commission_rate=None,
                    fee_algo=None,
                    fee_per_night=None,
                    db=self.db,
                    _=None,
                ))

        parsed_by_platform = {row.platform: row for row in response.data.platforms}
        self.assertEqual(set(parsed_by_platform), {"抖音", "美团", "携程"})
        for parsed in parsed_by_platform.values():
            self.assertTrue(parsed.daily_json)
            self.assertEqual(
                parsed.def_service_fee,
                Decimal(parsed.room_nights) * Decimal("30.00"),
            )
            self.assertEqual(
                parsed.def_jinying,
                parsed.def_hexiao + parsed.def_service_fee,
            )

        rows = []
        for parsed in response.data.platforms:
            rows.append({
                "platform": parsed.platform,
                "room_nights": parsed.room_nights,
                "base_received": parsed.base_received,
                "supplier_commission": parsed.suggested_commission,
                "daily_json": parsed.daily_json,
                "period_start": parsed.period_start,
                "period_end": parsed.period_end,
                "period_text": parsed.period_text,
                "check_date_text": parsed.check_date_text,
                "order_count": parsed.order_count,
                "positive_count": parsed.positive_count,
                "source_file": response.data.source_file,
                "detail_stored": response.data.detail_stored,
                "detail_name": response.data.detail_name,
            })
        hotel_api.save_ledger(
            scenic_id,
            HotelSaveIn(rows=rows, mode="append"),
            db=self.db,
            current_user=SimpleNamespace(id=1),
        )

        saved_rows = self.db.scalars(
            select(HotelLedger).where(HotelLedger.scenic_id == scenic_id)
        ).all()
        self.assertEqual(len(saved_rows), 3)
        snapshots = {}
        for saved in saved_rows:
            parsed = parsed_by_platform[saved.platform]
            self.assertEqual(saved.hexiao_amount, parsed.def_hexiao)
            self.assertEqual(saved.service_fee, parsed.def_service_fee)
            self.assertEqual(saved.jinying_amount, parsed.def_jinying)
            self.assertEqual(saved.rate_hexiao, Decimal("0.9000"))
            self.assertEqual(saved.rate_settle, Decimal("0.9100"))
            self.assertEqual(saved.commission_rate, Decimal("0.0600"))
            self.assertEqual(saved.fee_algo, 1)
            self.assertEqual(saved.fee_per_night, Decimal("30.00"))
            snapshots[saved.id] = (
                saved.hexiao_amount,
                saved.service_fee,
                saved.jinying_amount,
            )

        config.rate_settle = Decimal("0.5000")
        config.fee_per_night = Decimal("99.00")
        self.db.commit()
        with patch.object(
            hotel_api.scenic_config_svc,
            "get_effective_scenic_config",
            side_effect=AssertionError("历史酒店台账查询不应读取景区配置"),
        ):
            ledger = hotel_api.get_ledger(scenic_id, db=self.db, _=None)
        self.assertEqual(ledger.data.total, 3)
        for saved in saved_rows:
            self.db.refresh(saved)
            self.assertEqual(
                (
                    saved.hexiao_amount,
                    saved.service_fee,
                    saved.jinying_amount,
                ),
                snapshots[saved.id],
            )

    def test_request_parameters_override_scenic_config(self) -> None:
        scenic_id = "hotel-explicit-test"
        self._add_config(scenic_id)
        saved = self._save(
            scenic_id,
            rate_hexiao=Decimal("0.8000"),
            rate_settle=Decimal("0.9200"),
            commission_rate=Decimal("0.0500"),
            fee_algo=2,
            fee_per_night=Decimal("40.00"),
        )

        self.assertEqual(saved.rate_hexiao, Decimal("0.8000"))
        self.assertEqual(saved.rate_settle, Decimal("0.9200"))
        self.assertEqual(saved.commission_rate, Decimal("0.0500"))
        self.assertEqual(saved.fee_algo, 2)
        self.assertEqual(saved.fee_per_night, Decimal("40.00"))
        self.assertEqual(saved.hexiao_amount, Decimal("80.00"))
        self.assertEqual(saved.jinying_amount, Decimal("92.00"))
        self.assertEqual(saved.service_fee, Decimal("12.00"))

    def test_parse_request_parameters_override_scenic_config(self) -> None:
        scenic_id = "hotel-parse-explicit-test"
        self._add_config(scenic_id)
        parsed_result = {
            "platforms": [{"platform": "美团", "daily_json": "{}"}],
            "warnings": [],
        }

        with TemporaryDirectory() as temp_dir, patch.object(
            hotel_api,
            "_detail_dir",
            return_value=Path(temp_dir) / scenic_id,
        ), patch.object(
            hotel_api.hl_svc,
            "parse_hotel_file",
            return_value=parsed_result,
        ) as parse_mock:
            asyncio.run(hotel_api.parse_file(
                scenic_id,
                [UploadFile(filename="hotel.xlsx", file=io.BytesIO(b"xlsx"))],
                rate_hexiao=Decimal("0.8000"),
                rate_settle=Decimal("0.9200"),
                commission_rate=Decimal("0.0500"),
                fee_algo=2,
                fee_per_night=Decimal("40.00"),
                db=self.db,
                _=None,
            ))

        params = parse_mock.call_args.kwargs
        self.assertEqual(params["rate_hexiao"], Decimal("0.8000"))
        self.assertEqual(params["rate_settle"], Decimal("0.9200"))
        self.assertEqual(params["commission_rate"], Decimal("0.0500"))
        self.assertEqual(params["fee_algo"], 2)
        self.assertEqual(params["fee_per_night"], Decimal("40.00"))

    def test_missing_config_uses_current_system_defaults(self) -> None:
        saved = self._save("hotel-fallback-test")

        self.assertEqual(saved.rate_hexiao, hotel_service.DEFAULT_RATE_HEXIAO)
        self.assertEqual(saved.rate_settle, hotel_service.DEFAULT_RATE_SETTLE)
        self.assertEqual(saved.commission_rate, hotel_service.DEFAULT_COMMISSION_RATE)
        self.assertEqual(saved.fee_algo, 1)
        self.assertEqual(saved.fee_per_night, hotel_service.DEFAULT_FEE_PER_NIGHT)
        self.assertEqual(saved.hexiao_amount, Decimal("90.00"))
        self.assertEqual(saved.service_fee, Decimal("88.00"))
        self.assertEqual(saved.jinying_amount, Decimal("178.00"))


if __name__ == "__main__":
    unittest.main()
