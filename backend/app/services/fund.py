"""Pure aggregation and maturity-status functions for fund transactions."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from app.schemas.fund import DUE_CATEGORIES, FundSummary


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
