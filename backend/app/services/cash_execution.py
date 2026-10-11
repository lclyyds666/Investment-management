"""Idempotent creation of cash execution tasks from approved sources."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import ContractStatus, ContractType, InvoiceApprovalStatus, InvoiceDirection
from app.models.approval_form import ApprovalForm
from app.models.cash_execution import CashExecutionTask, CashTaskStatus
from app.models.invoice import Invoice


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _insert_or_reload(db: Session, task: CashExecutionTask, statement):
    try:
        with db.begin_nested():
            db.add(task)
            db.flush()
        return task
    except IntegrityError:
        return db.scalar(statement)


def ensure_payment_task(db: Session, form: ApprovalForm) -> CashExecutionTask | None:
    if form.form_type != ContractType.PAYMENT or form.status != ContractStatus.APPROVED:
        return None
    statement = select(CashExecutionTask).where(
        CashExecutionTask.approval_form_id == form.id
    )
    existing = db.scalar(statement)
    if existing is not None:
        return existing
    task = CashExecutionTask(
        direction="outflow",
        approval_form_id=form.id,
        contract_id=form.contract_id,
        scenic_id=form.scenic_id or "",
        planned_amount=_money(form.amount),
        executed_amount=Decimal("0.00"),
        status=CashTaskStatus.PENDING.value,
    )
    return _insert_or_reload(db, task, statement)


def ensure_receipt_task(db: Session, invoice: Invoice) -> CashExecutionTask | None:
    if (
        invoice.direction != InvoiceDirection.OUTPUT
        or invoice.approval_status != InvoiceApprovalStatus.APPROVED
        or not invoice.attachments
    ):
        return None
    statement = select(CashExecutionTask).where(CashExecutionTask.invoice_id == invoice.id)
    existing = db.scalar(statement)
    if existing is not None:
        return existing
    task = CashExecutionTask(
        direction="inflow",
        invoice_id=invoice.id,
        contract_id=invoice.contract_id,
        scenic_id=invoice.scenic_id or "",
        planned_amount=_money(invoice.amount),
        executed_amount=Decimal("0.00"),
        status=CashTaskStatus.PENDING.value,
    )
    return _insert_or_reload(db, task, statement)
