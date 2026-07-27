from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import UploadFile
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints import ticket_ledger as ticket_api
from app.db.base import Base
from app.models.scenic_config import ScenicConfig
from app.models.ticket_ledger import TicketLedger
from app.models.user import User
from app.schemas.ticket_ledger import TicketLedgerSaveIn
from app.services import ticket_ledger as ticket_service


REPO_ROOT = Path(__file__).resolve().parents[2]
EXCEL_BASELINES = {
    "对账明细-2026.04.29-2026.05.19.xlsx": {
        "supplier_received": "5082745.52",
        "suggested_commission": "267903.31",
        "def_hexiao": "4333358.00",
        "def_service_fee": "192593.68",
        "def_jinying": "4525951.68",
        "order_count": "17683",
        "positive_count": "17673",
        "period_text": "2026/4/29-2026/5/19",
    },
    "对账明细-2026.05.20-2026.06.23.xlsx": {
        "supplier_received": "2737638.19",
        "suggested_commission": "141633.90",
        "def_hexiao": "2336403.86",
        "def_service_fee": "103840.15",
        "def_jinying": "2440244.01",
        "order_count": "13005",
        "positive_count": "13002",
        "period_text": "2026/5/20-2026/6/23",
    },
    "对账明细-2026.06.24-2026.07.xlsx": {
        "supplier_received": "3289070.31",
        "suggested_commission": "160012.79",
        "def_hexiao": "2816151.76",
        "def_service_fee": "125162.30",
        "def_jinying": "2941314.06",
        "order_count": "14825",
        "positive_count": "14819",
        "period_text": "2026/6/24-2026/7/14",
    },
}


class TicketScenicConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, ScenicConfig.__table__, TicketLedger.__table__],
        )
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _add_config(
        self,
        scenic_id: str,
        rate_hexiao: str = "0.8800",
        rate_settle: str = "0.9300",
        commission_rate: str = "0.0500",
    ) -> ScenicConfig:
        row = ScenicConfig(
            scenic_id=scenic_id,
            scenic_name="测试景区",
            rate_hexiao=Decimal(rate_hexiao),
            rate_settle=Decimal(rate_settle),
            commission_rate=Decimal(commission_rate),
            hotel_fee_algo=1,
            fee_per_night=Decimal("44.00"),
            enabled=True,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def _save(self, scenic_id: str, **row_values) -> TicketLedger:
        values = {
            "platform": "抖音",
            "supplier_received": Decimal("100.00"),
            "supplier_commission": Decimal("0.00"),
        }
        values.update(row_values)
        ticket_api.save_ledger(
            scenic_id,
            TicketLedgerSaveIn(rows=[values], mode="append"),
            db=self.db,
            current_user=SimpleNamespace(id=1),
        )
        return self.db.scalar(
            select(TicketLedger)
            .where(TicketLedger.scenic_id == scenic_id)
            .order_by(TicketLedger.id.desc())
        )

    def test_save_uses_config_and_persists_rate_snapshot(self) -> None:
        config = self._add_config("configured-scenic")
        saved = self._save("configured-scenic")

        self.assertEqual(saved.rate_hexiao, Decimal("0.8800"))
        self.assertEqual(saved.rate_settle, Decimal("0.9300"))
        self.assertEqual(saved.commission_rate, Decimal("0.0500"))
        self.assertEqual(saved.hexiao_amount, Decimal("88.00"))
        self.assertEqual(saved.jinying_amount, Decimal("93.00"))

        config.rate_hexiao = Decimal("0.5000")
        config.rate_settle = Decimal("0.6000")
        config.commission_rate = Decimal("0.0100")
        self.db.commit()
        new_saved = self._save("configured-scenic")
        self.db.refresh(saved)

        self.assertEqual(saved.hexiao_amount, Decimal("88.00"))
        self.assertEqual(saved.jinying_amount, Decimal("93.00"))
        self.assertEqual(saved.rate_hexiao, Decimal("0.8800"))
        self.assertEqual(saved.rate_settle, Decimal("0.9300"))
        self.assertEqual(saved.commission_rate, Decimal("0.0500"))
        self.assertEqual(new_saved.hexiao_amount, Decimal("50.00"))
        self.assertEqual(new_saved.jinying_amount, Decimal("60.00"))

    def test_request_rates_override_config(self) -> None:
        self._add_config("explicit-scenic")
        saved = self._save(
            "explicit-scenic",
            rate_hexiao=Decimal("0.8100"),
            rate_settle=Decimal("0.9100"),
            commission_rate=Decimal("0.0400"),
        )

        self.assertEqual(saved.rate_hexiao, Decimal("0.8100"))
        self.assertEqual(saved.rate_settle, Decimal("0.9100"))
        self.assertEqual(saved.commission_rate, Decimal("0.0400"))
        self.assertEqual(saved.hexiao_amount, Decimal("81.00"))
        self.assertEqual(saved.jinying_amount, Decimal("91.00"))

    def test_missing_config_uses_current_system_constants(self) -> None:
        saved = self._save("fallback-scenic")

        self.assertEqual(saved.rate_hexiao, ticket_service.DEFAULT_RATE_HEXIAO)
        self.assertEqual(saved.rate_settle, ticket_service.DEFAULT_RATE_SETTLE)
        self.assertEqual(saved.commission_rate, ticket_service.DEFAULT_COMMISSION_RATE)
        self.assertEqual(saved.hexiao_amount, Decimal("90.00"))
        self.assertEqual(saved.jinying_amount, Decimal("94.00"))

    def test_historical_query_does_not_read_scenic_config(self) -> None:
        self._add_config("history-scenic")
        self._save("history-scenic")

        with patch.object(
            ticket_api.scenic_config_svc,
            "get_effective_scenic_config",
            side_effect=AssertionError("历史查询不应读取景区配置"),
        ):
            response = ticket_api.get_ledger("history-scenic", db=self.db, _=None)

        self.assertEqual(response.data.total, 1)
        self.assertEqual(response.data.rows[0].hexiao_amount, Decimal("88.00"))

    def test_parse_daily_json_matches_saved_amounts(self) -> None:
        scenic_id = "daily-regression-scenic"
        self._add_config(
            scenic_id,
            rate_hexiao="0.8800",
            rate_settle="0.9100",
            commission_rate="0.0500",
        )
        historical = self._save(
            "existing-history",
            rate_hexiao=Decimal("0.9000"),
            rate_settle=Decimal("0.9400"),
            commission_rate=Decimal("0.0600"),
        )
        historical_snapshot = (
            historical.hexiao_amount,
            historical.jinying_amount,
            historical.service_fee,
        )
        path = REPO_ROOT / "台账" / "对账明细-2026.04.29-2026.05.19.xlsx"

        with TemporaryDirectory() as temp_dir, path.open("rb") as stream:
            with patch.object(
                ticket_api,
                "_detail_dir",
                return_value=Path(temp_dir) / scenic_id,
            ):
                response = asyncio.run(ticket_api.parse_files(
                    scenic_id,
                    [UploadFile(filename=path.name, file=stream)],
                    rate_hexiao=None,
                    rate_settle=None,
                    commission_rate=None,
                    db=self.db,
                    _=None,
                ))

        parsed = response.data.files[0]
        self.assertTrue(parsed.daily_json)
        self.assertEqual(parsed.positive_count, 17673)

        ticket_api.save_ledger(
            scenic_id,
            TicketLedgerSaveIn(rows=[{
                "platform": "抖音",
                "supplier_received": parsed.supplier_received,
                "supplier_commission": parsed.suggested_commission,
                "check_date_text": parsed.check_date_text,
                "period_text": parsed.period_text,
                "period_start": parsed.period_start,
                "period_end": parsed.period_end,
                "daily_json": parsed.daily_json,
                "order_count": parsed.order_count,
                "positive_count": parsed.positive_count,
                "source_file": parsed.source_file,
                "detail_stored": parsed.detail_stored,
                "detail_name": parsed.detail_name,
            }], mode="append"),
            db=self.db,
            current_user=SimpleNamespace(id=1),
        )
        saved = self.db.scalar(
            select(TicketLedger).where(TicketLedger.scenic_id == scenic_id)
        )

        self.assertEqual(saved.hexiao_amount, parsed.def_hexiao)
        self.assertEqual(saved.jinying_amount, parsed.def_jinying)
        self.assertEqual(saved.service_fee, parsed.def_service_fee)
        self.db.refresh(historical)
        self.assertEqual(
            (
                historical.hexiao_amount,
                historical.jinying_amount,
                historical.service_fee,
            ),
            historical_snapshot,
        )


class TicketExcelRegressionTest(unittest.TestCase):
    def test_quanzhou_excel_results_match_prechange_baseline(self) -> None:
        result_keys = (
            "supplier_received",
            "suggested_commission",
            "def_hexiao",
            "def_service_fee",
            "def_jinying",
            "order_count",
            "positive_count",
            "period_text",
        )
        for filename, expected in EXCEL_BASELINES.items():
            with self.subTest(filename=filename):
                path = REPO_ROOT / "台账" / filename
                actual = ticket_service.parse_reconciliation(
                    path.read_bytes(),
                    filename=filename,
                    rate_hexiao=Decimal("0.90"),
                    rate_settle=Decimal("0.94"),
                    commission_rate=Decimal("0.06"),
                )
                actual_values = {key: str(actual[key]) for key in result_keys}
                self.assertEqual(actual_values, expected)


if __name__ == "__main__":
    unittest.main()
