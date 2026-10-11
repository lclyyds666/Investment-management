from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.init_db  # noqa: F401
from app.core.enums import ContractStatus, ContractType, InvoiceDirection, InvoiceSourceKind, InvoiceStatus
from app.db.base import Base
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.hotel_ledger import HotelLedger
from app.models.invoice import Invoice, InvoiceAttachment, InvoiceDetail
from app.models.invoice_preference import ScenicInvoicePreference
from app.models.ledger_contract import LedgerContractLink
from app.models.ticket_ledger import TicketLedger
from app.models.user import User
from app.services.invoice_generation import (
    InvoiceSourceLocked,
    invalidate_period_invoices,
    remove_period_invoices,
    sync_confirmed_period_invoices,
)


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    return Session(engine)


def _link_contract(db, *, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p"):
    user = User(username=f"owner-{source_kind.value}-{period_key}", hashed_password="x")
    contract = Contract(
        contract_no=f"HT-{source_kind.value}-{period_key}",
        title="景区合同",
        scenic_id=scenic_id,
        business_scopes=[source_kind.value],
        status=ContractStatus.APPROVED,
        created_by=1,
    )
    db.add(user)
    db.flush()
    contract.created_by = user.id
    db.add(contract)
    db.flush()
    db.add(LedgerContractLink(
        scenic_id=scenic_id,
        source_kind=source_kind,
        period_key=period_key,
        contract_id=contract.id,
        contract_no_snapshot=contract.contract_no,
        selected_by=user.id,
    ))
    db.flush()
    return contract


def test_ticket_period_generation_ignores_total_and_is_idempotent():
    db = _session()
    contract = _link_contract(db)
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
    assert input_invoice.contract_id == contract.id
    assert input_invoice.contract_no == contract.contract_no
    assert output.contract_id == contract.id
    assert output.contract_no == contract.contract_no
    assert [(item.platform, item.source_row_id, item.amount) for item in output.details] == [
        ("A", 2, Decimal("2.00")),
        ("B", 1, Decimal("3.00")),
    ]


def test_hotel_period_generation_uses_hotel_source_kind():
    db = _session()
    contract = _link_contract(db, source_kind=InvoiceSourceKind.HOTEL)
    db.add(HotelLedger(scenic_id="s", row_no=1, platform="A", source_file="p", hexiao_amount=4, jinying_amount=6))
    db.flush()
    input_invoice, output_invoice = sync_confirmed_period_invoices(
        db, scenic_id="s", source_kind=InvoiceSourceKind.HOTEL, period_key="p"
    )
    assert input_invoice.source_kind == InvoiceSourceKind.HOTEL
    assert output_invoice.amount == Decimal("6.00")
    assert input_invoice.contract_id == contract.id
    assert output_invoice.contract_no == contract.contract_no


def test_ticket_and_hotel_same_period_are_isolated():
    db = _session()
    _link_contract(db, source_kind=InvoiceSourceKind.TICKET, period_key="same")
    _link_contract(db, source_kind=InvoiceSourceKind.HOTEL, period_key="same")
    db.add_all([
        TicketLedger(scenic_id="s", row_no=1, platform="A", source_file="same", hexiao_amount=1, jinying_amount=2),
        HotelLedger(scenic_id="s", row_no=1, platform="A", source_file="same", hexiao_amount=3, jinying_amount=4),
    ])
    db.flush()
    sync_confirmed_period_invoices(db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="same")
    sync_confirmed_period_invoices(db, scenic_id="s", source_kind=InvoiceSourceKind.HOTEL, period_key="same")
    assert db.scalar(select(func.count()).select_from(Invoice)) == 4


def test_remove_unused_period_cleans_dependents():
    db = _session()
    contract = _link_contract(db)
    db.add_all([
        ScenicInvoicePreference(
            scenic_id="s", direction=InvoiceDirection.OUTPUT, last_contract_no="  missing  "
        ),
        TicketLedger(scenic_id="s", row_no=1, platform="A", source_file="p", hexiao_amount=1, jinying_amount=2),
    ])
    db.flush()
    _, output = sync_confirmed_period_invoices(
        db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p"
    )
    assert output.contract_no == contract.contract_no
    assert output.contract_id == contract.id
    output.attachments.append(InvoiceAttachment(original_name="a.pdf", stored_name="a"))
    db.commit()
    remove_period_invoices(db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p")
    db.commit()
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0
    assert db.scalar(select(func.count()).select_from(InvoiceAttachment)) == 0
    assert db.scalar(select(func.count()).select_from(InvoiceDetail)) == 0
    assert db.scalar(select(func.count()).select_from(ApprovalForm)) == 0


def test_used_source_invoice_cannot_be_invalidated_or_rebuilt():
    db = _session()
    _link_contract(db)
    db.add(TicketLedger(
        scenic_id="s", row_no=1, platform="A", source_file="p",
        hexiao_amount=1, jinying_amount=2, confirmed=True,
    ))
    db.flush()
    input_invoice, _ = sync_confirmed_period_invoices(
        db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p"
    )
    original_id = input_invoice.id
    input_invoice.status = InvoiceStatus.ISSUED
    db.flush()

    with pytest.raises(InvoiceSourceLocked):
        invalidate_period_invoices(
            db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p"
        )
    with pytest.raises(InvoiceSourceLocked):
        sync_confirmed_period_invoices(
            db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p"
        )

    assert db.get(Invoice, original_id) is input_invoice
    assert db.scalar(select(TicketLedger.confirmed)) is True


def test_source_invoice_with_approval_form_cannot_be_removed():
    db = _session()
    contract = _link_contract(db)
    db.add(TicketLedger(
        scenic_id="s", row_no=1, platform="A", source_file="p",
        hexiao_amount=1, jinying_amount=2,
    ))
    db.flush()
    _, output_invoice = sync_confirmed_period_invoices(
        db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p"
    )
    db.add(ApprovalForm(
        form_type=ContractType.INVOICE,
        invoice_id=output_invoice.id,
        created_by=contract.created_by,
    ))
    db.flush()

    with pytest.raises(InvoiceSourceLocked):
        remove_period_invoices(
            db, scenic_id="s", source_kind=InvoiceSourceKind.TICKET, period_key="p"
        )
