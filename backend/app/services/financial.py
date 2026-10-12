"""Financial dashboard aggregation backed only by scenic ledger snapshots."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger
from app.services.invoice_generation import hotel_period_key, ticket_period_key
from app.services.scenic_analytics import build_financial_metrics


def _decimal_value(value) -> Decimal:
    return Decimal(str(value or 0))


def _period_rank(rows: list) -> tuple:
    representative = max(
        rows,
        key=lambda row: (
            row.period_end is not None,
            row.period_end or date.min,
            row.period_start is not None,
            row.period_start or date.min,
            row.created_at or datetime.min,
            row.id or 0,
        ),
    )
    return (
        representative.period_end is not None,
        representative.period_end or date.min,
        representative.period_start is not None,
        representative.period_start or date.min,
        representative.created_at or datetime.min,
        representative.id or 0,
    )


def _completion_for_kind(rows, business_type: str, period_key) -> list[dict]:
    by_scenic = defaultdict(list)
    for row in rows:
        by_scenic[row.scenic_id].append(row)

    result = []
    for scenic_id, scenic_rows in by_scenic.items():
        cumulative = sum(
            (_decimal_value(row.hexiao_amount) for row in scenic_rows), Decimal("0")
        )
        periods = defaultdict(list)
        for row in scenic_rows:
            periods[period_key(row)].append(row)
        latest_rows = max(periods.values(), key=_period_rank)
        latest = max(
            latest_rows,
            key=lambda row: (row.created_at or datetime.min, row.id or 0),
        )
        pending = _decimal_value(latest.pending_writeoff)
        denominator = cumulative + pending
        rate = None if denominator == 0 else (
            cumulative / denominator * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        result.append({
            "scenic_id": scenic_id,
            "business_type": business_type,
            "cumulative_writeoff": cumulative.quantize(Decimal("0.01")),
            "pending_writeoff": pending.quantize(Decimal("0.01")),
            "completion_rate": rate,
        })
    return result


def build_scenic_completion(
    ticket_rows: list[TicketLedger], hotel_rows: list[HotelLedger]
) -> list[dict]:
    details = [
        *_completion_for_kind(ticket_rows, "ticket", ticket_period_key),
        *_completion_for_kind(hotel_rows, "hotel", hotel_period_key),
    ]
    return sorted(details, key=lambda item: (item["scenic_id"], item["business_type"]))


def build_ledger_metrics(
    ticket_rows: list[TicketLedger],
    hotel_rows: list[HotelLedger],
    *,
    today: date | None = None,
) -> dict:
    """Preserve the dashboard API while sharing the canonical aggregation logic."""
    metrics = build_financial_metrics(ticket_rows, hotel_rows, today=today)
    metrics["scenic_completion"] = build_scenic_completion(ticket_rows, hotel_rows)
    return metrics


def build_dashboard(db: Session) -> dict:
    ticket_rows = db.scalars(
        select(TicketLedger).order_by(TicketLedger.period_start, TicketLedger.id)
    ).all()
    hotel_rows = db.scalars(
        select(HotelLedger).order_by(HotelLedger.period_start, HotelLedger.id)
    ).all()
    return build_ledger_metrics(ticket_rows, hotel_rows)
