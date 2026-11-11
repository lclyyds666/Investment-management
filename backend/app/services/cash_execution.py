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
from app.models.fund import FundTransaction


class CashExecutionError(ValueError):
    pass


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


def execute_task(db: Session, task_id: int, payload, actor_id: int) -> FundTransaction:
    task = db.scalar(
        select(CashExecutionTask)
        .where(CashExecutionTask.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not task or task.status in {
        CashTaskStatus.COMPLETED.value,
        CashTaskStatus.CANCELLED.value,
    }:
        raise CashExecutionError("task_not_executable")
    amount = _money(payload.amount)
    remaining = _money(task.planned_amount) - _money(task.executed_amount)
    if amount <= 0 or amount > remaining:
        raise CashExecutionError("amount_exceeds_remaining")
    fund = FundTransaction(
        direction="usage" if task.direction == "outflow" else "increase",
        category="business_payment" if task.direction == "outflow" else "customer_payment",
        amount=amount,
        occurred_on=payload.occurred_on,
        counterparty=payload.counterparty,
        summary=payload.summary,
        remark=payload.remark,
        bank_reference=payload.bank_reference,
        execution_task_id=task.id,
        contract_id=task.contract_id,
        approval_form_id=task.approval_form_id,
        invoice_id=task.invoice_id,
        scenic_id=task.scenic_id,
        created_by=actor_id,
    )
    task.executed_amount = _money(task.executed_amount) + amount
    task.status = (
        CashTaskStatus.COMPLETED.value
        if task.executed_amount == task.planned_amount
        else CashTaskStatus.PARTIAL.value
    )
    db.add(fund)
    db.flush()
    return fund
