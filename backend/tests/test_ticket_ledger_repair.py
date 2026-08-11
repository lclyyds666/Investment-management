import json
import unittest
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openpyxl import Workbook

from app.models.ticket_ledger import TicketLedger
from app.services import ticket_ledger_repair as repair


CALCULATED_FIELDS = (
    "supplier_received",
    "supplier_commission",
    "publisher_due",
    "hexiao_amount",
    "jinying_amount",
    "service_fee",
    "daily_json",
    "order_count",
    "positive_count",
)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.flush_count = 0

    def scalars(self, _statement):
        return _Rows(self.rows)

    def flush(self):
        self.flush_count += 1


def _daily(received: str, eligible: str | None = None) -> str:
    day = {
        "r": received,
        "s": received,
        "d": "-2",
        "t": "-1",
    }
    if eligible is not None:
        day.update({"cs": eligible, "cd": "-2", "ct": "-1"})
    return json.dumps([day], ensure_ascii=False)


def _automatic_row(
    *,
    row_id: int = 1,
    scenic_id: str = "zunyi-zoo",
    platform: str = "抖音",
    source_file: str = "period-1.xlsx",
    detail_stored: str = "period-1.xlsx",
) -> TicketLedger:
    daily_json = _daily("100")
    calculated = repair.tl_svc.recompute_from_json(
        daily_json,
        Decimal("0.90"),
        Decimal("0.94"),
        None,
        Decimal("0.06"),
        platform,
        scenic_id=scenic_id,
    )
    return TicketLedger(
        id=row_id,
        scenic_id=scenic_id,
        row_no=row_id,
        platform=platform,
        ticket_product="测试门票",
        check_date_text="2026/7/1-2026/7/7",
        period_text="2026/7/1-2026/7/7",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 7),
        supplier_received=Decimal("100.00"),
        supplier_commission=calculated["supplier_commission"],
        commission_rate=Decimal("0.06"),
        publisher_due=calculated["publisher_due"],
        hexiao_amount=calculated["hexiao_amount"],
        payment_amount=Decimal("500.00"),
        co_investment_amount=Decimal("0"),
        pending_writeoff=Decimal("0"),
        jinying_amount=calculated["jinying_amount"],
        service_fee=calculated["service_fee"],
        rate_hexiao=Decimal("0.90"),
        rate_settle=Decimal("0.94"),
        rate_fee=Decimal("0.04"),
        order_count=1,
        positive_count=1,
        daily_json=daily_json,
        source_file=source_file,
        detail_stored=detail_stored,
        detail_name=source_file,
    )


def _platform_info(platform: str = "抖音") -> dict:
    return {
        "platform": platform,
        "supplier_received": Decimal("110.00"),
        "daily_json": _daily("110", "110"),
        "order_count": 2,
        "positive_count": 1,
    }


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "同程"
    sheet.append(["订单金额", "张数", "核销时间"])
    sheet.append([100, 1, date(2026, 7, 1)])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class TicketLedgerRepairPlanningTest(unittest.TestCase):
    def test_automatic_values_are_replanned_from_corrected_snapshot(self):
        row = _automatic_row()

        item = repair.plan_repair_row(row, _platform_info())

        self.assertEqual(item.after["supplier_received"], Decimal("110.00"))
        self.assertEqual(item.after["daily_json"], _platform_info()["daily_json"])
        self.assertEqual(item.after["order_count"], 2)
        self.assertEqual(item.after["positive_count"], 1)
        self.assertFalse(item.protected_supplier_received)
        self.assertFalse(item.protected_commission)
        self.assertFalse(item.protected_hexiao)
        self.assertFalse(item.protected_jinying)

    def test_fuzhou_production_snapshot_has_exact_planned_values(self):
        old_calc = {
            "supplier_commission": Decimal("96151.26"),
            "publisher_due": Decimal("1106862.23"),
            "hexiao_amount": Decimal("1007244.62"),
            "jinying_amount": Decimal("1051519.13"),
            "service_fee": Decimal("44274.51"),
        }
        expected = {
            "supplier_received": Decimal("1203013.49"),
            "supplier_commission": Decimal("94542.38"),
            "publisher_due": Decimal("1108471.11"),
            "hexiao_amount": Decimal("1008708.69"),
            "jinying_amount": Decimal("1053047.54"),
            "service_fee": Decimal("44338.85"),
        }
        row = _automatic_row(scenic_id="fuzhou-ouleb")
        row.daily_json = json.dumps([{"r": "1203013.49"}])
        for field, value in old_calc.items():
            setattr(row, field, value)
        row.supplier_received = expected["supplier_received"]
        row.commission_rate = Decimal("0.08")
        platform_info = {
            "platform": "抖音",
            "supplier_received": expected["supplier_received"],
            "daily_json": json.dumps([{"r": "1203013.49", "cs": "0"}]),
            "order_count": 2,
            "positive_count": 1,
        }

        with patch.object(
            repair.tl_svc,
            "recompute_from_json",
            side_effect=[old_calc, expected],
        ):
            item = repair.plan_repair_row(row, platform_info)

        self.assertEqual(
            {field: item.after[field] for field in expected},
            expected,
        )

    def test_manual_values_are_protected_and_linked_fields_follow_them(self):
        row = _automatic_row()
        row.supplier_received = Decimal("125.00")
        row.supplier_commission = Decimal("8.00")
        row.hexiao_amount = Decimal("80.00")
        row.jinying_amount = Decimal("120.00")

        item = repair.plan_repair_row(row, _platform_info())

        self.assertTrue(item.protected_supplier_received)
        self.assertTrue(item.protected_commission)
        self.assertTrue(item.protected_hexiao)
        self.assertTrue(item.protected_jinying)
        self.assertEqual(item.after["supplier_received"], Decimal("125.00"))
        self.assertEqual(item.after["supplier_commission"], Decimal("8.00"))
        self.assertEqual(item.after["publisher_due"], Decimal("117.00"))
        self.assertEqual(item.after["hexiao_amount"], Decimal("80.00"))
        self.assertEqual(item.after["jinying_amount"], Decimal("120.00"))
        self.assertEqual(item.after["service_fee"], Decimal("40.00"))

    def test_tongcheng_manual_commission_is_used_for_automatic_downstream(self):
        row = _automatic_row(platform="同程")
        row.supplier_commission = Decimal("8.00")

        item = repair.plan_repair_row(row, _platform_info("同程"))

        self.assertTrue(item.protected_commission)
        self.assertEqual(item.after["supplier_received"], Decimal("110.00"))
        self.assertEqual(item.after["supplier_commission"], Decimal("8.00"))
        self.assertEqual(item.after["publisher_due"], Decimal("102.00"))
        self.assertEqual(item.after["hexiao_amount"], Decimal("91.80"))
        self.assertEqual(item.after["jinying_amount"], Decimal("95.88"))
        self.assertEqual(item.after["service_fee"], Decimal("4.08"))

    def test_supplier_received_protection_uses_unrounded_tolerance(self):
        row = _automatic_row()
        row.daily_json = _daily("100.005")
        old_calc = repair.tl_svc.recompute_from_json(
            row.daily_json,
            row.rate_hexiao,
            row.rate_settle,
            None,
            row.commission_rate,
            row.platform,
            scenic_id=row.scenic_id,
        )
        row.supplier_received = Decimal("100.00")
        for field in (
            "supplier_commission",
            "publisher_due",
            "hexiao_amount",
            "jinying_amount",
            "service_fee",
        ):
            setattr(row, field, old_calc[field])

        item = repair.plan_repair_row(row, _platform_info())

        self.assertFalse(item.protected_supplier_received)

    def test_replanning_an_applied_item_is_idempotent(self):
        row = _automatic_row()
        platform_info = _platform_info()
        first = repair.plan_repair_row(row, platform_info)
        for field, value in first.after.items():
            setattr(row, field, value)

        second = repair.plan_repair_row(row, platform_info)

        self.assertEqual(
            {field: second.before[field] for field in CALCULATED_FIELDS},
            {field: second.after[field] for field in CALCULATED_FIELDS},
        )


class TicketLedgerRepairOrchestrationTest(unittest.TestCase):
    def test_build_validates_every_source_before_mutating_rows(self):
        valid = _automatic_row(detail_stored="valid.xlsx")
        missing = _automatic_row(row_id=2, detail_stored="missing.xlsx")
        session = _Session([valid, missing])
        snapshot = {
            row.id: {field: getattr(row, field) for field in CALCULATED_FIELDS}
            for row in session.rows
        }

        with TemporaryDirectory() as temp_dir:
            detail_dir = Path(temp_dir) / "ticket_detail_zunyi-zoo"
            detail_dir.mkdir()
            (detail_dir / "valid.xlsx").write_bytes(_workbook_bytes())
            with self.assertRaisesRegex(ValueError, "missing.xlsx"):
                repair.build_repair_plan(session, Path(temp_dir))

        self.assertEqual(
            snapshot,
            {
                row.id: {field: getattr(row, field) for field in CALCULATED_FIELDS}
                for row in session.rows
            },
        )

    def test_build_rejects_path_traversal(self):
        row = _automatic_row(detail_stored="../outside.xlsx")

        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "basename"):
                repair.build_repair_plan(_Session([row]), Path(temp_dir))

    def test_build_parses_each_source_once_and_matches_platforms(self):
        douyin = _automatic_row(detail_stored="shared.xlsx")
        tongcheng = _automatic_row(
            row_id=2,
            platform="同程",
            detail_stored="shared.xlsx",
        )
        parsed = {
            "platforms": [_platform_info("抖音"), _platform_info("同程")],
        }

        with TemporaryDirectory() as temp_dir:
            detail_dir = Path(temp_dir) / "ticket_detail_zunyi-zoo"
            detail_dir.mkdir()
            (detail_dir / "shared.xlsx").write_bytes(b"workbook")
            with patch.object(
                repair.tl_svc, "parse_reconciliation", return_value=parsed
            ) as parse:
                items = repair.build_repair_plan(
                    _Session([douyin, tongcheng]), Path(temp_dir)
                )

        self.assertEqual(len(items), 2)
        parse.assert_called_once()

    def test_apply_updates_fields_flushes_once_and_groups_period_balances(self):
        period_one_douyin = _automatic_row()
        period_one_tongcheng = _automatic_row(row_id=2, platform="同程")
        period_two = _automatic_row(
            row_id=3,
            source_file="period-2.xlsx",
            detail_stored="period-2.xlsx",
        )
        period_two.period_start = date(2026, 7, 8)
        period_two.period_end = date(2026, 7, 14)
        period_two.period_text = "2026/7/8-2026/7/14"
        period_two.check_date_text = period_two.period_text
        period_two.payment_amount = Decimal("0")
        items = []
        for row, writeoff in (
            (period_one_douyin, Decimal("90.00")),
            (period_one_tongcheng, Decimal("180.00")),
            (period_two, Decimal("45.00")),
        ):
            before = {field: getattr(row, field) for field in CALCULATED_FIELDS}
            after = dict(before, hexiao_amount=writeoff)
            items.append(
                repair.RepairPlanItem(
                    row=row,
                    before=before,
                    after=after,
                    protected_supplier_received=False,
                    protected_commission=False,
                    protected_hexiao=False,
                    protected_jinying=False,
                )
            )
        session = _Session(
            [period_one_douyin, period_one_tongcheng, period_two]
        )

        repair.apply_repair_plan(session, items)

        self.assertEqual(session.flush_count, 1)
        self.assertEqual(period_one_douyin.hexiao_amount, Decimal("90.00"))
        self.assertEqual(period_one_tongcheng.hexiao_amount, Decimal("180.00"))
        self.assertEqual(period_two.hexiao_amount, Decimal("45.00"))
        self.assertEqual(period_one_douyin.pending_writeoff, Decimal("230.00"))
        self.assertEqual(period_one_tongcheng.pending_writeoff, Decimal("230.00"))
        self.assertEqual(period_two.pending_writeoff, Decimal("185.00"))

    def test_format_excludes_snapshot_contents_and_lists_protection(self):
        row = _automatic_row(row_id=77, scenic_id="fuzhou-ouleb")
        row.period_text = "2026/7/2-2026/7/25"
        before = {field: getattr(row, field) for field in CALCULATED_FIELDS}
        after = dict(
            before,
            supplier_commission=Decimal("4.00"),
            publisher_due=Decimal("96.00"),
            daily_json="secret corrected snapshot",
        )
        item = repair.RepairPlanItem(
            row=row,
            before=before,
            after=after,
            protected_supplier_received=True,
            protected_commission=False,
            protected_hexiao=False,
            protected_jinying=False,
        )

        output = repair.format_repair_plan([item])

        self.assertIn(
            "row=77 scenic=fuzhou-ouleb platform=抖音 period=2026/7/2-2026/7/25",
            output,
        )
        self.assertIn("supplier_commission: 3.00 -> 4.00", output)
        self.assertIn("publisher_due: 97.00 -> 96.00", output)
        self.assertIn("protected: supplier_received", output)
        self.assertNotIn("secret corrected snapshot", output)
        self.assertNotIn("daily_json", output)


if __name__ == "__main__":
    unittest.main()
