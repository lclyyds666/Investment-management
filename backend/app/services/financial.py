"""Financial dashboard aggregation backed only by scenic ledger snapshots."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger
from app.services.scenic_analytics import build_financial_metrics


def build_ledger_metrics(
    ticket_rows: list[TicketLedger],
    hotel_rows: list[HotelLedger],
    *,
    today: date | None = None,
) -> dict:
    """Preserve the dashboard API while sharing the canonical aggregation logic."""
    return build_financial_metrics(ticket_rows, hotel_rows, today=today)


def build_dashboard(db: Session) -> dict:
    ticket_rows = db.scalars(
        select(TicketLedger).order_by(TicketLedger.period_start, TicketLedger.id)
    ).all()
    hotel_rows = db.scalars(
        select(HotelLedger).order_by(HotelLedger.period_start, HotelLedger.id)
    ).all()
    return build_ledger_metrics(ticket_rows, hotel_rows)
