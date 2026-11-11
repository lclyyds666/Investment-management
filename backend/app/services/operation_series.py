"""Confirmed ledger rows expanded into immutable daily operation points."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class OperationDailyPoint:
    day: date
    scenic_id: str
    business_type: str
    platform: str
    settlement_amount: Decimal
    writeoff_amount: Decimal
    order_count: int


@dataclass(frozen=True)
class DataQualityIssue:
    row_id: object
    business_type: str
    code: str


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def _split_decimal(total: Decimal, days: int) -> list[Decimal]:
    # Apportion whole cents; signed corrections retain their original sign.
    cents = int((abs(total) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    quotient, remainder = divmod(cents, days)
    sign = Decimal("-1") if total < 0 else Decimal("1")
    return [sign * Decimal(quotient + (index < remainder)) / 100 for index in range(days)]


def _split_count(total: int, days: int) -> list[int]:
    quotient, remainder = divmod(max(total, 0), days)
    return [quotient + (1 if index < remainder else 0) for index in range(days)]


def build_confirmed_daily_series(ticket_rows, hotel_rows):
    points, issues = [], []
    for business_type, rows in (("ticket", ticket_rows), ("hotel", hotel_rows)):
        for row in rows:
            if not getattr(row, "confirmed", False):
                continue
            start = _as_date(getattr(row, "period_start", None))
            end = _as_date(getattr(row, "period_end", None))
            if not start or not end or end < start:
                issues.append(DataQualityIssue(getattr(row, "id", None), business_type, "missing_period_dates"))
                continue
            dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
            settlements = _split_decimal(Decimal(getattr(row, "jinying_amount", 0) or 0), len(dates))
            writeoffs = _split_decimal(Decimal(getattr(row, "hexiao_amount", 0) or 0), len(dates))
            orders = _split_count(int(getattr(row, "order_count", 0) or 0), len(dates))
            points.extend(
                OperationDailyPoint(
                    day=day,
                    scenic_id=getattr(row, "scenic_id", ""),
                    business_type=business_type,
                    platform=getattr(row, "platform", "") or "",
                    settlement_amount=settlements[index],
                    writeoff_amount=writeoffs[index],
                    order_count=orders[index],
                )
                for index, day in enumerate(dates)
            )
    return points, issues
