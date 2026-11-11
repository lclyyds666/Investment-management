"""Fund integrity, historical associations and maturity reporting."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.fund import FundTransaction
from app.models.fund_alert import FundAlertReceipt
from app.models.cash_execution import InvoiceFundAllocation
from app.models.approval_form import ApprovalForm
from app.core.enums import ContractStatus, ContractType
from app.services.contract_eligibility import ContractEligibilityError, eligible_contract_for_user
from app.schemas.fund import (
    DUE_CATEGORIES,
    FundAlertItem,
    FundAlertReceiptItem,
    FundAlertToday,
    FundSummary,
)


BUSINESS_CATEGORIES = frozenset({"business_payment", "customer_payment"})


class FundIntegrityError(ValueError):
    pass


def locked_fund(db: Session, fund_id: int) -> FundTransaction | None:
    # Match reconciliation's fund row lock; refresh cached objects after waiting.
    return db.scalar(select(FundTransaction).where(FundTransaction.id == fund_id)
                     .with_for_update().execution_options(populate_existing=True))


def has_allocations(db: Session, fund_id: int) -> bool:
    # A locking read sees allocations committed while we waited for the fund lock
    # even under MySQL REPEATABLE READ (a plain aggregate may use an old snapshot).
    return bool(db.scalars(select(InvoiceFundAllocation.id).where(
        InvoiceFundAllocation.fund_transaction_id == fund_id
    ).with_for_update()).all())


def validate_fund_edit(db: Session, row: FundTransaction, changes: dict) -> None:
    if changes.get("category", row.category) in BUSINESS_CATEGORIES and changes.get("category", row.category) != row.category:
        raise FundIntegrityError("business_cash_requires_execution_task")
    protected = {"amount", "direction", "category", "contract_id", "scenic_id"}
    if row.execution_task_id:
        # Only summary/remark corrections are generic edits; preserve execution
        # date, counterparty and bank evidence as well as financial/source fields.
        protected |= {"occurred_on", "counterparty", "bank_reference", "maturity_date",
                      "execution_task_id", "approval_form_id", "invoice_id"}
    changed = {key for key, value in changes.items() if getattr(row, key) != value}
    if row.execution_task_id and changed & protected:
        raise FundIntegrityError("execution_fund_fields_locked")
    if changed & protected and has_allocations(db, row.id):
        raise FundIntegrityError("fund_allocated_unallocate_first")


def associate_legacy_fund(db: Session, row: FundTransaction, payload, actor) -> None:
    if row.execution_task_id:
        raise FundIntegrityError("execution_fund_fields_locked")
    if row.category not in BUSINESS_CATEGORIES:
        raise FundIntegrityError("legacy_business_fund_required")
    try:
        contract = eligible_contract_for_user(db, actor, payload.contract_id, for_update=True)
    except ContractEligibilityError as error:
        raise FundIntegrityError("approved_scenic_contract_required") from error
    if not contract.scenic_id or not contract.business_scopes:
        raise FundIntegrityError("approved_scenic_contract_required")
    if row.scenic_id and row.scenic_id != contract.scenic_id:
        raise FundIntegrityError("scenic_mismatch")
    if row.contract_id not in (None, contract.id):
        raise FundIntegrityError("legacy_contract_already_linked")
    expected = "usage" if row.category == "business_payment" else "increase"
    if row.direction != expected:
        raise FundIntegrityError("direction_mismatch")
    if row.approval_form_id not in (None, payload.approval_form_id):
        raise FundIntegrityError("legacy_approval_already_linked")
    if payload.approval_form_id:
        form = db.scalar(select(ApprovalForm).where(ApprovalForm.id == payload.approval_form_id)
                         .with_for_update().execution_options(populate_existing=True))
        if (row.direction != "usage" or not form or form.form_type != ContractType.PAYMENT
                or form.status != ContractStatus.APPROVED or form.contract_id != contract.id
                or form.scenic_id != contract.scenic_id):
            raise FundIntegrityError("payment_approval_mismatch")
    changes = {"contract_id": contract.id, "scenic_id": contract.scenic_id,
               "approval_form_id": payload.approval_form_id}
    if has_allocations(db, row.id) and any(getattr(row, key) != value for key, value in changes.items()):
        raise FundIntegrityError("fund_allocated_unallocate_first")
    for key, value in changes.items():
        setattr(row, key, value)


def maturity_state(row, today: date) -> str:
    """Return the alert state for one fund transaction as of *today*."""
    if row.settlement_status == "settled":
        return "settled"
    if row.category not in DUE_CATEGORIES or not row.maturity_date:
        return "normal"
    days = (row.maturity_date - today).days
    if days < 0:
        return "overdue"
    return "due_soon" if days <= 30 else "normal"


def summarize_funds(rows: Iterable, today: date) -> FundSummary:
    """Aggregate fund balances and maturity alerts without mutating ledger rows."""
    total_increase = Decimal("0")
    total_usage = Decimal("0")
    due_within_30_amount = Decimal("0")
    due_within_30_count = 0
    overdue_count = 0

    for row in rows:
        amount = Decimal(row.amount)
        if row.direction == "increase":
            total_increase += amount
        elif row.direction == "usage":
            total_usage += amount

        state = maturity_state(row, today)
        if state == "due_soon":
            due_within_30_amount += amount
            due_within_30_count += 1
        elif state == "overdue":
            overdue_count += 1

    return FundSummary(
        available_funds=total_increase - total_usage,
        total_increase=total_increase,
        total_usage=total_usage,
        due_within_30_amount=due_within_30_amount,
        due_within_30_count=due_within_30_count,
        overdue_count=overdue_count,
    )


def build_fund_alert_item(row, today: date) -> FundAlertItem | None:
    stage = maturity_state(row, today)
    if stage not in {"due_soon", "overdue"}:
        return None
    return FundAlertItem(
        id=row.id,
        category=row.category,
        counterparty=row.counterparty or "",
        summary=row.summary or "",
        amount=Decimal(row.amount),
        maturity_date=row.maturity_date,
        days_remaining=(row.maturity_date - today).days,
        stage=stage,
    )


def list_today_alerts(db: Session, user_id: int, today: date) -> FundAlertToday:
    rows = db.scalars(
        select(FundTransaction)
        .where(
            FundTransaction.category.in_(DUE_CATEGORIES),
            FundTransaction.settlement_status == "open",
            FundTransaction.maturity_date <= today + timedelta(days=30),
        )
        .order_by(FundTransaction.maturity_date.asc(), FundTransaction.id.asc())
    ).all()
    receipts = db.execute(
        select(FundAlertReceipt.fund_id, FundAlertReceipt.stage).where(
            FundAlertReceipt.user_id == user_id,
            FundAlertReceipt.alert_date == today,
        )
    ).all()
    shown = {(fund_id, stage) for fund_id, stage in receipts}
    items = [item for row in rows if (item := build_fund_alert_item(row, today))]
    return FundAlertToday(
        alert_date=today,
        items=[item for item in items if (item.id, item.stage) not in shown],
    )


def acknowledge_alert_receipts(
    db: Session,
    user_id: int,
    items: list[FundAlertReceiptItem],
    today: date,
) -> int:
    acknowledged = 0
    requested = {(item.fund_id, item.stage) for item in items}
    for fund_id, stage in sorted(requested):
        row = db.get(FundTransaction, fund_id, with_for_update=True)
        current = build_fund_alert_item(row, today) if row else None
        if current is None or current.stage != stage:
            continue
        exists = db.scalar(
            select(FundAlertReceipt.id).where(
                FundAlertReceipt.user_id == user_id,
                FundAlertReceipt.fund_id == fund_id,
                FundAlertReceipt.alert_date == today,
                FundAlertReceipt.stage == stage,
            )
        )
        if exists is not None:
            continue
        try:
            with db.begin_nested():
                db.add(FundAlertReceipt(
                    user_id=user_id,
                    fund_id=fund_id,
                    alert_date=today,
                    stage=stage,
                ))
                db.flush()
        except IntegrityError:
            duplicate = db.scalar(
                select(FundAlertReceipt.id).where(
                    FundAlertReceipt.user_id == user_id,
                    FundAlertReceipt.fund_id == fund_id,
                    FundAlertReceipt.alert_date == today,
                    FundAlertReceipt.stage == stage,
                )
            )
            if duplicate is None:
                raise
            continue
        acknowledged += 1
    return acknowledged
