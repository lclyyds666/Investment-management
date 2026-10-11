from __future__ import annotations

from typing import Any

from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from app.core.enums import InvoiceSourceKind
from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger


def ledger_model(source_kind: InvoiceSourceKind):
    if source_kind == InvoiceSourceKind.TICKET:
        return TicketLedger
    if source_kind == InvoiceSourceKind.HOTEL:
        return HotelLedger
    raise ValueError(f"unsupported invoice source kind: {source_kind}")


def ledger_period_key(row: Any) -> str:
    return (
        row.source_file
        or row.detail_name
        or row.period_text
        or row.check_date_text
        or "NA"
    )


def ledger_period_key_from_values(
    *,
    source_file: str | None = None,
    detail_name: str | None = None,
    period_text: str | None = None,
    check_date_text: str | None = None,
) -> str:
    return source_file or detail_name or period_text or check_date_text or "NA"


def period_rows_for_update_statement(
    source_kind: InvoiceSourceKind,
    scenic_id: str,
    period_key: str,
):
    model = ledger_model(source_kind)
    key_expression = func.coalesce(
        func.nullif(model.source_file, ""),
        func.nullif(model.detail_name, ""),
        func.nullif(model.period_text, ""),
        func.nullif(model.check_date_text, ""),
        literal("NA"),
    )
    return (
        select(model)
        .where(model.scenic_id == scenic_id, key_expression == period_key)
        .order_by(model.id.asc())
        .with_for_update()
    )


def lock_period_rows(
    db: Session,
    *,
    scenic_id: str,
    source_kind: InvoiceSourceKind,
    period_key: str,
) -> list[Any]:
    return db.scalars(
        period_rows_for_update_statement(source_kind, scenic_id, period_key)
        .execution_options(populate_existing=True)
    ).all()


def lock_period_rows_for_row(
    db: Session,
    *,
    scenic_id: str,
    source_kind: InvoiceSourceKind,
    row_id: int,
) -> tuple[Any | None, list[Any], str | None]:
    model = ledger_model(source_kind)
    candidate = db.scalar(
        select(model).where(model.id == row_id, model.scenic_id == scenic_id)
    )
    if candidate is None:
        return None, [], None
    period_key = ledger_period_key(candidate)
    rows = lock_period_rows(
        db,
        scenic_id=scenic_id,
        source_kind=source_kind,
        period_key=period_key,
    )
    locked = next((row for row in rows if row.id == row_id), None)
    if locked is None:
        return None, rows, period_key
    return locked, rows, period_key


def lock_scenic_rows(
    db: Session,
    *,
    scenic_id: str,
    source_kind: InvoiceSourceKind,
) -> list[Any]:
    model = ledger_model(source_kind)
    statement = (
        select(model)
        .where(model.scenic_id == scenic_id)
        .order_by(model.id.asc())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return db.scalars(statement).all()
