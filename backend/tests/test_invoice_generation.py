from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.init_db  # noqa: F401
from app.core.enums import InvoiceDirection, InvoiceSourceKind
from app.db.base import Base
from app.models.hotel_ledger import HotelLedger
from app.models.invoice import Invoice
from app.models.ticket_ledger import TicketLedger
from app.services.invoice_generation import sync_confirmed_period_invoices


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_ticket_period_generation_ignores_total_and_is_idempotent():
    db = _session()
    db.add_all(
        [
            TicketLedger(scenic_id="s", row_no=2, platform="B", source_file="p", hexiao_amount=2, jinying_amount=3),
            TicketLedger(scenic_id="s", row_no=1, platform="A", source_file="p", hexiao_amount=1, jinying_amount=2),
            TicketLedger(scenic_id="s", row_no=3, platform="\u5408\u8ba1", source_file="p", hexiao_amount=100, jinying_amount=100),
        ]
    )
    db.flush()
    first = sync_confirmed_period_invoices(
        db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p"
    )
    second = sync_confirmed_period_invoices(
        db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p"
    )
    rows = db.scalars(select(Invoice).where(Invoice.scenic_id == "s")).all()
    output = next(item for item in second if item.direction == InvoiceDirection.OUTPUT)
    assert len(rows) == 2
    assert output.amount == Decimal("5.00")
    assert [(item.platform, item.source_row_id, item.amount) for item in output.details] == [
        ("A", 2, Decimal("2.00")),
        ("B", 1, Decimal("3.00")),
    ]


def test_hotel_period_generation_uses_hotel_source_kind():
    db = _session()
    db.add(HotelLedger(scenic_id="s", row_no=1, platform="A", source_file="p", hexiao_amount=4, jinying_amount=6))
    db.flush()
    input_invoice, output_invoice = sync_confirmed_period_invoices(
        db, scenic_id="s", source_kind=InvoiceSourceKind.HOTEL, period_key="p"
    )
    assert input_invoice.source_kind == InvoiceSourceKind.HOTEL
    assert output_invoice.amount == Decimal("6.00")
