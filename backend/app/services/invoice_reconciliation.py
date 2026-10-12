"""Invoice and fund transaction reconciliation."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.enums import InvoiceDirection
from app.models.cash_execution import InvoiceFundAllocation
from app.models.fund import FundTransaction
from app.models.invoice import Invoice


class ReconciliationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def allocated_to_invoice(db: Session, invoice_id: int) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(InvoiceFundAllocation.amount), 0)).where(
            InvoiceFundAllocation.invoice_id == invoice_id
        )
    )
    return money(value)


def allocated_from_fund(db: Session, fund_id: int) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(InvoiceFundAllocation.amount), 0)).where(
            InvoiceFundAllocation.fund_transaction_id == fund_id
        )
    )
    return money(value)


def invoice_reconciliation_state(db: Session, invoice: Invoice) -> str:
    allocated = allocated_to_invoice(db, invoice.id)
    if allocated <= 0:
        return "unallocated"
    if allocated < money(invoice.amount):
        return "partial"
    return "allocated"


def invoice_unallocated_amount(db: Session, invoice: Invoice) -> Decimal:
    return max(money(invoice.amount) - allocated_to_invoice(db, invoice.id), Decimal("0.00"))


def list_allocations(db: Session, invoice_id: int) -> list[InvoiceFundAllocation]:
    return list(db.scalars(
        select(InvoiceFundAllocation)
        .where(InvoiceFundAllocation.invoice_id == invoice_id)
        .options(joinedload(InvoiceFundAllocation.fund_transaction))
        .order_by(InvoiceFundAllocation.id)
    ).unique().all())


def allocate(
    db: Session,
    invoice_id: int,
    fund_id: int,
    amount,
    actor_id: int,
) -> InvoiceFundAllocation:
    invoice = db.scalar(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    )
    fund = db.scalar(
        select(FundTransaction).where(FundTransaction.id == fund_id).with_for_update()
    )
    if invoice is None or fund is None:
        raise ReconciliationError("source_not_found")
    expected_direction = "usage" if invoice.direction == InvoiceDirection.INPUT else "increase"
    if fund.direction != expected_direction:
        raise ReconciliationError("direction_mismatch")
    if invoice.contract_id and fund.contract_id and invoice.contract_id != fund.contract_id:
        raise ReconciliationError("contract_mismatch")
    value = money(amount)
    invoice_remaining = money(invoice.amount) - allocated_to_invoice(db, invoice.id)
    fund_remaining = money(fund.amount) - allocated_from_fund(db, fund.id)
    if value <= 0 or value > invoice_remaining or value > fund_remaining:
        raise ReconciliationError("allocation_exceeds_remaining")
    allocation = InvoiceFundAllocation(
        fund_transaction_id=fund.id,
        invoice_id=invoice.id,
        amount=value,
        allocated_by=actor_id,
    )
    db.add(allocation)
    db.flush()
    return allocation


def delete_allocation(db: Session, invoice_id: int, allocation_id: int) -> None:
    allocation = db.scalar(
        select(InvoiceFundAllocation)
        .where(
            InvoiceFundAllocation.id == allocation_id,
            InvoiceFundAllocation.invoice_id == invoice_id,
        )
        .with_for_update()
    )
    if allocation is None:
        raise ReconciliationError("allocation_not_found")
    db.delete(allocation)
    db.flush()
