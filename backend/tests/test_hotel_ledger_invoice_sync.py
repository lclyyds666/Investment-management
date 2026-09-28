from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.db.init_db  # noqa: F401
from app.api.v1.endpoints.hotel_ledger import approve_confirm, delete_row, update_row
from app.db.base import Base
from app.models.hotel_ledger import HotelLedger
from app.models.invoice import Invoice
from app.schemas.hotel_ledger import HotelUpdateIn
from app.services.invoice_generation import hotel_period_key


def test_hotel_period_key_matches_ledger_grouping_rule():
    class Row:
        source_file = ""
        detail_name = ""
        period_text = "period"
        check_date_text = "date"

    assert hotel_period_key(Row()) == "period"


def _confirmed_period():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    rows = [
        HotelLedger(scenic_id="s", row_no=1, platform="A", source_file="p", hexiao_amount=1, jinying_amount=2, confirm_stored="c.pdf"),
        HotelLedger(scenic_id="s", row_no=2, platform="B", source_file="p", hexiao_amount=3, jinying_amount=4, confirm_stored="c.pdf"),
    ]
    db.add_all(rows)
    db.commit()
    approve_confirm("s", rows[0].id, db=db, _=None)
    return db, rows


def test_approve_then_update_unconfirms_hotel_period():
    db, rows = _confirmed_period()
    update_row("s", rows[0].id, HotelUpdateIn(jinying_amount=Decimal("9")), db=db, _=None)
    db.expire_all()
    assert all(not row.confirmed for row in db.scalars(select(HotelLedger)).all())
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0


def test_delete_unconfirms_surviving_hotel_rows():
    db, rows = _confirmed_period()
    delete_row("s", rows[0].id, db=db, _=None)
    survivor = db.scalar(select(HotelLedger))
    assert survivor is not None and not survivor.confirmed
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0
