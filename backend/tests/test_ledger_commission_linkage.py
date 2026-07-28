import json
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from app.api.v1.endpoints import hotel_ledger as hotel_api
from app.api.v1.endpoints import ticket_ledger as ticket_api
from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger
from app.schemas.hotel_ledger import HotelUpdateIn
from app.schemas.ticket_ledger import TicketLedgerUpdateIn


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, row):
        self.row = row
        self.commit_count = 0

    def scalar(self, _statement):
        return self.row

    def scalars(self, _statement):
        return _Rows([self.row])

    def flush(self):
        return None

    def commit(self):
        self.commit_count += 1

    def refresh(self, _row):
        return None


def _daily_json():
    return json.dumps(
        [
            {"r": "100", "s": "100", "d": "-2", "t": "-1", "n": 1, "b": "100"},
            {"r": "50", "s": "50", "d": "-1", "t": "0", "n": 2, "b": "50"},
        ]
    )


def _ticket_row():
    return TicketLedger(
        id=1,
        scenic_id="test-scenic",
        row_no=1,
        pay_date=date(2026, 1, 1),
        platform="抖音",
        ticket_product="测试门票",
        check_date_text="2026-01",
        period_text="2026-01",
        supplier_received=Decimal("150"),
        supplier_commission=Decimal("6"),
        commission_rate=Decimal("0.06"),
        publisher_due=Decimal("144"),
        hexiao_amount=Decimal("129.60"),
        payment_amount=Decimal("100"),
        pending_writeoff=Decimal("-29.60"),
        jinying_amount=Decimal("135.36"),
        service_fee=Decimal("5.76"),
        rate_hexiao=Decimal("0.90"),
        rate_settle=Decimal("0.94"),
        rate_fee=Decimal("0.04"),
        order_count=2,
        positive_count=2,
        repay_date=date(2026, 1, 2),
        repay_amount=Decimal("10"),
        daily_json=_daily_json(),
        confirm_stored="",
        confirm_name="",
        confirmed=False,
        source_file="ticket.xlsx",
        detail_stored="ticket.xlsx",
        detail_name="ticket.xlsx",
        created_at=datetime(2026, 1, 1),
    )


def _hotel_row():
    return HotelLedger(
        id=2,
        scenic_id="test-scenic",
        row_no=1,
        platform="抖音",
        hotel_name="测试酒店",
        check_date_text="2026-01",
        period_text="2026-01",
        room_nights=3,
        base_received=Decimal("150"),
        supplier_commission=Decimal("6"),
        commission_rate=Decimal("0.06"),
        settle_base=Decimal("144"),
        rate_hexiao=Decimal("0.90"),
        hexiao_amount=Decimal("129.60"),
        fee_algo=1,
        fee_per_night=Decimal("44"),
        rate_settle=Decimal("0.94"),
        service_fee=Decimal("132"),
        jinying_amount=Decimal("261.60"),
        payment_amount=Decimal("200"),
        payment_date=date(2026, 1, 1),
        pending_writeoff=Decimal("70.40"),
        repay_date=date(2026, 1, 2),
        repay_amount=Decimal("10"),
        order_count=2,
        positive_count=2,
        daily_json=_daily_json(),
        confirm_stored="",
        confirm_name="",
        confirmed=False,
        source_file="hotel.xlsx",
        detail_stored="hotel.xlsx",
        detail_name="hotel.xlsx",
        created_at=datetime(2026, 1, 1),
    )


class CommissionLinkageTest(unittest.TestCase):
    def test_ticket_rate_preview_and_update_use_same_daily_result(self):
        row = _ticket_row()
        payload = TicketLedgerUpdateIn(
            pay_date=None,
            platform="抖音",
            commission_rate=Decimal("0.05"),
            rate_hexiao=Decimal("0.90"),
            rate_settle=Decimal("0.94"),
            payment_amount=Decimal("100"),
            repay_date=None,
            repay_amount=None,
        )
        preview = ticket_api._calculation_preview(row, payload)
        self.assertEqual(preview.supplier_commission, Decimal("3.50"))
        self.assertEqual(preview.publisher_due, Decimal("146.50"))

        session = _Session(row)
        ticket_api.update_row("test-scenic", row.id, payload, session, None)
        self.assertEqual(row.supplier_commission, preview.supplier_commission)
        self.assertEqual(row.publisher_due, preview.publisher_due)
        self.assertEqual(row.hexiao_amount, preview.hexiao_amount)
        self.assertEqual(row.jinying_amount, preview.jinying_amount)
        self.assertEqual(row.service_fee, preview.service_fee)
        self.assertEqual(row.commission_rate, Decimal("0.05"))
        self.assertIsNone(row.pay_date)
        self.assertIsNone(row.repay_date)
        self.assertIsNone(row.repay_amount)
        self.assertEqual(session.commit_count, 1)

    def test_hotel_rate_preview_and_update_use_same_daily_result(self):
        row = _hotel_row()
        payload = HotelUpdateIn(
            hotel_name="新酒店名称",
            room_nights=3,
            commission_rate=Decimal("0.05"),
            rate_hexiao=Decimal("0.90"),
            fee_algo=1,
            fee_per_night=Decimal("44"),
            rate_settle=Decimal("0.94"),
            payment_amount=Decimal("200"),
            payment_date=None,
            repay_date=None,
            repay_amount=None,
        )
        preview = hotel_api._calculation_preview(row, payload)
        self.assertEqual(preview.supplier_commission, Decimal("3.50"))
        self.assertEqual(preview.settle_base, Decimal("146.50"))

        session = _Session(row)
        hotel_api.update_row("test-scenic", row.id, payload, session, None)
        self.assertEqual(row.hotel_name, "新酒店名称")
        self.assertEqual(row.supplier_commission, preview.supplier_commission)
        self.assertEqual(row.settle_base, preview.settle_base)
        self.assertEqual(row.hexiao_amount, preview.hexiao_amount)
        self.assertEqual(row.jinying_amount, preview.jinying_amount)
        self.assertEqual(row.service_fee, preview.service_fee)
        self.assertEqual(row.commission_rate, Decimal("0.05"))
        self.assertIsNone(row.payment_date)
        self.assertIsNone(row.repay_date)
        self.assertIsNone(row.repay_amount)
        self.assertEqual(session.commit_count, 1)

    def test_non_douyin_commission_is_zero(self):
        row = _ticket_row()
        payload = TicketLedgerUpdateIn(
            platform="美团",
            commission_rate=Decimal("0.50"),
            supplier_commission=Decimal("999"),
        )
        preview = ticket_api._calculation_preview(row, payload)
        self.assertEqual(preview.supplier_commission, Decimal("0"))

    def test_ticket_missing_daily_snapshot_is_recovered_before_update(self):
        row = _ticket_row()
        row.daily_json = ""
        payload = TicketLedgerUpdateIn(
            platform="抖音",
            commission_rate=Decimal("0.05"),
        )
        with patch.object(ticket_api, "_recover_daily_json", return_value=_daily_json()):
            preview = ticket_api._calculation_preview(row, payload)
            session = _Session(row)
            ticket_api.update_row("test-scenic", row.id, payload, session, None)
        self.assertEqual(preview.supplier_commission, Decimal("3.50"))
        self.assertEqual(row.supplier_commission, preview.supplier_commission)
        self.assertEqual(row.daily_json, _daily_json())


if __name__ == "__main__":
    unittest.main()
