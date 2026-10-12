"""Pure aggregation and maturity-status functions for fund transactions."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.fund import FundTransaction
from app.models.fund_alert import FundAlertReceipt
from app.schemas.fund import (
    DUE_CATEGORIES,
    FundAlertItem,
    FundAlertReceiptItem,
    FundAlertToday,
    FundSummary,
)


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
