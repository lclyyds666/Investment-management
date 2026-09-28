from decimal import Decimal

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.init_db  # noqa: F401
from app.core.enums import ContractType, InvoiceDirection, InvoiceSourceKind
from app.db.base import Base
from app.models.approval_form import ApprovalForm
from app.models.hotel_ledger import HotelLedger
from app.models.invoice import Invoice, InvoiceAttachment, InvoiceDetail
from app.models.invoice_preference import ScenicInvoicePreference
from app.models.ticket_ledger import TicketLedger
from app.models.user import User
from app.services.invoice_generation import remove_period_invoices, sync_confirmed_period_invoices


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
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
    input_invoice = next(item for item in second if item.direction == InvoiceDirection.INPUT)
    assert len(rows) == 2
    assert input_invoice.amount == Decimal("3.00")
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


def test_ticket_and_hotel_same_period_are_isolated():
    db = _session()
    db.add_all([
        TicketLedger(scenic_id="s", row_no=1, platform="A", source_file="same", hexiao_amount=1, jinying_amount=2),
        HotelLedger(scenic_id="s", row_no=1, platform="A", source_file="same", hexiao_amount=3, jinying_amount=4),
    ])
    db.flush()
    sync_confirmed_period_invoices(db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="same")
    sync_confirmed_period_invoices(db, scenic_id="s", source_kind=InvoiceSourceKind.HOTEL, period_key="same")
    assert db.scalar(select(func.count()).select_from(Invoice)) == 4


def test_remove_period_cleans_dependents_and_stale_preference_is_blank():
    db = _session()
    user = User(username="owner", hashed_password="x")
    db.add_all([
        user,
        ScenicInvoicePreference(
            scenic_id="s", direction=InvoiceDirection.OUTPUT, last_contract_no="  missing  "
        ),
        TicketLedger(scenic_id="s", row_no=1, platform="A", source_file="p", hexiao_amount=1, jinying_amount=2),
    ])
    db.flush()
    _, output = sync_confirmed_period_invoices(
        db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p"
    )
    assert output.contract_no == ""
    assert output.customer_id is None
    output.attachments.append(InvoiceAttachment(original_name="a.pdf", stored_name="a"))
    db.add(ApprovalForm(form_type=ContractType.INVOICE, invoice_id=output.id, created_by=user.id))
    db.commit()
    remove_period_invoices(db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p")
    db.commit()
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0
    assert db.scalar(select(func.count()).select_from(InvoiceAttachment)) == 0
    assert db.scalar(select(func.count()).select_from(InvoiceDetail)) == 0
    assert db.scalar(select(func.count()).select_from(ApprovalForm)) == 0
