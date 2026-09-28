"""Generate source-backed invoice snapshots from confirmed ledger periods."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.enums import (
    InvoiceApprovalStatus,
    InvoiceDirection,
    InvoiceSourceKind,
    InvoiceStatus,
)
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.hotel_ledger import HotelLedger
from app.models.invoice import Invoice, InvoiceDetail
from app.models.invoice_preference import ScenicInvoicePreference
from app.models.ticket_ledger import TicketLedger
from app.models.approval_form import ApprovalForm


def ticket_period_key(row: TicketLedger) -> str:
    return row.source_file or row.detail_name or row.period_text or row.check_date_text or "NA"


def hotel_period_key(row: HotelLedger) -> str:
    return row.source_file or row.detail_name or row.period_text or row.check_date_text or "NA"


def _is_platform_row(row) -> bool:
    value = str(getattr(row, "platform", "") or "").strip()
    if not value:
        return False
    return value.casefold() not in {"合计", "总计", "小计", "total", "subtotal"}


def _period_rows(db: Session, source_kind: InvoiceSourceKind, scenic_id: str, period_key: str):
    if source_kind == InvoiceSourceKind.TICKET:
        rows = db.scalars(
            select(TicketLedger).where(TicketLedger.scenic_id == scenic_id)
        ).all()
        key_fn = ticket_period_key
    elif source_kind == InvoiceSourceKind.HOTEL:
        rows = db.scalars(
            select(HotelLedger).where(HotelLedger.scenic_id == scenic_id)
        ).all()
        key_fn = hotel_period_key
    else:
        raise ValueError(f"unsupported invoice source kind: {source_kind}")
    return sorted(
        [row for row in rows if key_fn(row) == period_key],
        key=lambda row: (getattr(row, "row_no", 0) or 0, row.id),
    )


def _source_rows(db: Session, source_kind: InvoiceSourceKind, scenic_id: str, period_key: str):
    return [
        row
        for row in _period_rows(db, source_kind, scenic_id, period_key)
        if _is_platform_row(row)
    ]


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _fingerprint(rows, source_kind: InvoiceSourceKind) -> str:
    values = [
        {
            "id": row.id,
            "platform": str(row.platform or ""),
            "hexiao": str(_money(row.hexiao_amount)),
            "jinying": str(_money(row.jinying_amount)),
        }
        for row in rows
    ]
    payload = json.dumps([source_kind.value, values], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _remembered_customer(db: Session, scenic_id: str, direction: InvoiceDirection):
    preference = db.scalar(
        select(ScenicInvoicePreference).where(
            ScenicInvoicePreference.scenic_id == scenic_id,
            ScenicInvoicePreference.direction == direction,
        )
    )
    remembered_no = ((preference.last_contract_no if preference else "") or "").strip()
    if not remembered_no:
        return "", None
    contract = db.scalar(select(Contract).where(Contract.contract_no == remembered_no))
    if not contract:
        return "", None
    customer = None
    if contract.customer_credit_code:
        customer = db.scalar(
            select(Customer).where(Customer.social_credit_code == contract.customer_credit_code)
        )
    if not customer and contract.customer_name:
        customer = db.scalar(select(Customer).where(Customer.name == contract.customer_name))
    return contract.contract_no, customer


def _invoice_snapshot(
    *,
    direction: InvoiceDirection,
    source_kind: InvoiceSourceKind,
    scenic_id: str,
    period_key: str,
    amount: Decimal,
    source_revision: int,
    fingerprint: str,
    contract_no: str,
    customer: Customer | None,
) -> Invoice:
    invoice = Invoice(
        invoice_title="景区进项发票" if direction == InvoiceDirection.INPUT else "景区销项发票",
        amount=amount,
        status=InvoiceStatus.PENDING,
        direction=direction,
        source_kind=source_kind,
        scenic_id=scenic_id,
        period_key=period_key,
        source_revision=source_revision,
        source_fingerprint=fingerprint,
        generated_by_source=True,
        contract_no=contract_no,
        approval_status=InvoiceApprovalStatus.DRAFT,
        generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        source_synced_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    if customer:
        invoice.customer_id = customer.id
        invoice.customer_name = customer.name
        invoice.customer_social_credit_code = customer.social_credit_code or ""
        invoice.customer_address = customer.address or ""
        invoice.customer_phone = customer.phone or ""
        invoice.customer_bank_name = customer.bank_name or ""
        invoice.customer_bank_account = customer.bank_account or ""
    return invoice


def remove_period_invoices(
    db: Session,
    *,
    scenic_id: str,
    source_kind: InvoiceSourceKind,
    period_key: str,
) -> None:
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.scenic_id == scenic_id,
            Invoice.source_kind == source_kind,
            Invoice.period_key == period_key,
            Invoice.direction.in_((InvoiceDirection.INPUT, InvoiceDirection.OUTPUT)),
        )
    ).all()
    if not invoices:
        return
    ids = [invoice.id for invoice in invoices]
    db.execute(delete(ApprovalForm).where(ApprovalForm.invoice_id.in_(ids)))
    for invoice in invoices:
        db.delete(invoice)
    db.flush()


def sync_confirmed_period_invoices(
    db: Session,
    *,
    scenic_id: str,
    source_kind: InvoiceSourceKind,
    period_key: str,
) -> tuple[Invoice, Invoice]:
    rows = _source_rows(db, source_kind, scenic_id, period_key)
    if not rows:
        raise ValueError("cannot generate invoices for an empty source period")
    remove_period_invoices(
        db, scenic_id=scenic_id, source_kind=source_kind, period_key=period_key
    )
    fingerprint = _fingerprint(rows, source_kind)
    revision = max((row.id for row in rows), default=0)
    contract_no, customer = _remembered_customer(db, scenic_id, InvoiceDirection.OUTPUT)
    input_invoice = _invoice_snapshot(
        direction=InvoiceDirection.INPUT,
        source_kind=source_kind,
        scenic_id=scenic_id,
        period_key=period_key,
        amount=sum((_money(row.hexiao_amount) for row in rows), Decimal("0")),
        source_revision=revision,
        fingerprint=fingerprint,
        contract_no="",
        customer=None,
    )
    output_invoice = _invoice_snapshot(
        direction=InvoiceDirection.OUTPUT,
        source_kind=source_kind,
        scenic_id=scenic_id,
        period_key=period_key,
        amount=sum((_money(row.jinying_amount) for row in rows), Decimal("0")),
        source_revision=revision,
        fingerprint=fingerprint,
        contract_no=contract_no,
        customer=customer,
    )
    for line_no, row in enumerate(rows, start=1):
        output_invoice.details.append(
            InvoiceDetail(
                line_no=line_no,
                source_row_id=row.id,
                source_kind=source_kind,
                platform=row.platform or "",
                item_name=(getattr(row, "ticket_product", "") or getattr(row, "hotel_name", "") or ""),
                amount=_money(row.jinying_amount),
            )
        )
    db.add_all((input_invoice, output_invoice))
    db.flush()
    return input_invoice, output_invoice


def invalidate_period_invoices(
    db: Session,
    *,
    scenic_id: str,
    source_kind: InvoiceSourceKind,
    period_key: str,
) -> None:
    rows = _period_rows(db, source_kind, scenic_id, period_key)
    for row in rows:
        row.confirmed = False
    remove_period_invoices(
        db, scenic_id=scenic_id, source_kind=source_kind, period_key=period_key
    )
