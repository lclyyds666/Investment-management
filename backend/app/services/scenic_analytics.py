"""Aggregate-only scenic analytics shared by pages and the AI assistant."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger
from app.services.ai_dates import DateRange
from app.services.scenic_config import get_effective_config


_ZERO = Decimal("0")
_PERCENT = Decimal("100")
_LEDGER_DATE_RE = re.compile(r"(20\d{2})\D{0,3}(\d{1,2})(?:\D{0,3}(\d{1,2}))?")


@dataclass(frozen=True)
class ScenicSummary:
    scenic_id: str
    scenic_name: str
    requested_start: date
    requested_end: date
    covered_start: date | None
    covered_end: date | None
    data_updated_at: datetime | None
    partial_coverage: bool
    sales: Decimal
    writeoff_count: int
    positive_count: int
    writeoff_rate: Decimal
    existing_scale: Decimal
    realized_scale: Decimal
    gross_profit: Decimal
    capital_occupation_days: float | None
    ticket_total: Decimal
    hotel_total: Decimal


@dataclass(frozen=True)
class ScenicTrendPoint:
    scenic_id: str
    scenic_name: str
    dimension: Literal["month", "platform"]
    key: str
    label: str
    requested_start: date
    requested_end: date
    covered_start: date | None
    covered_end: date | None
    data_updated_at: datetime | None
    partial_coverage: bool
    sales: Decimal
    writeoff_count: int
    positive_count: int
    writeoff_rate: Decimal
    gross_profit: Decimal


def decimal_value(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def bounded_period_date(row) -> date | None:
    """Return the only date key allowed for date-bounded AI queries."""
    for value in (getattr(row, "period_end", None), getattr(row, "period_start", None)):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
    return None


def ledger_period_date(row) -> date | None:
    """Resolve a display month for the existing dashboard, including legacy text."""
    direct = bounded_period_date(row)
    if direct:
        return direct
    text = getattr(row, "period_text", "") or getattr(row, "check_date_text", "") or ""
    matches = list(_LEDGER_DATE_RE.finditer(text))
    match = matches[-1] if matches else None
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3) or 1))
        except ValueError:
            pass
    created = getattr(row, "created_at", None)
    if isinstance(created, datetime):
        return created.date()
    return created if isinstance(created, date) else None


def _period_label(row) -> str:
    label = getattr(row, "period_text", "") or getattr(row, "check_date_text", "")
    if label:
        return label
    start = getattr(row, "period_start", None)
    end = getattr(row, "period_end", None)
    if start or end:
        return f"{start or ''}~{end or ''}".strip("~")
    return f"台账#{getattr(row, 'id', '')}"


def _profit_point(
    scenic_id: str,
    business_type: str,
    row,
    service_fee: Decimal,
    realized_amount: Decimal,
    existing_scale: Decimal,
    occupation_weight: Decimal,
    occupation_amount: Decimal,
) -> dict:
    period_date = ledger_period_date(row)
    period = f"{period_date.month}月" if period_date else _period_label(row)
    date_key = period_date.strftime("%Y-%m") if period_date else f"undated::{period}"
    return {
        "scenic_id": scenic_id,
        "business_type": business_type,
        "period": period,
        "period_key": date_key,
        "year": period_date.year if period_date else None,
        "month": period_date.month if period_date else None,
        "service_fee": service_fee,
        "realized_amount": realized_amount,
        "existing_scale": existing_scale,
        "occupation_weight": occupation_weight,
        "occupation_amount": occupation_amount,
    }


def hotel_period_key(row) -> tuple[str, str]:
    period = (
        getattr(row, "source_file", "")
        or getattr(row, "detail_name", "")
        or getattr(row, "period_text", "")
        or getattr(row, "check_date_text", "")
        or f"row:{getattr(row, 'id', '')}"
    )
    return row.scenic_id, period


def occupation_values(
    net_investment: Decimal,
    start: date | None,
    end: date | None,
    today: date,
) -> tuple[Decimal, Decimal]:
    if net_investment <= 0 or not start:
        return _ZERO, _ZERO
    days = max(((end or today) - start).days, 0)
    return net_investment * Decimal(days), net_investment


def build_financial_metrics(
    ticket_rows: Sequence[TicketLedger],
    hotel_rows: Sequence[HotelLedger],
    *,
    today: date | None = None,
) -> dict:
    """Build existing dashboard metrics from immutable ledger snapshots."""
    today = today or date.today()
    total_invested = _ZERO
    total_realized = _ZERO
    total_gross = _ZERO
    occupation_weight = _ZERO
    occupation_amount = _ZERO
    ledger_profit: list[dict] = []

    def add_occupation(weight: Decimal, amount: Decimal) -> None:
        nonlocal occupation_weight, occupation_amount
        occupation_weight += weight
        occupation_amount += amount

    for row in ticket_rows:
        payment = decimal_value(row.payment_amount)
        co_investment = decimal_value(getattr(row, "co_investment_amount", 0))
        net_investment = payment - co_investment
        total_invested += net_investment
        total_realized += decimal_value(row.jinying_amount)
        total_gross += decimal_value(row.service_fee)
        row_occupation_weight, row_occupation_amount = occupation_values(
            net_investment, row.pay_date, row.repay_date, today,
        )
        add_occupation(row_occupation_weight, row_occupation_amount)
        ledger_profit.append(_profit_point(
            row.scenic_id, "ticket", row, decimal_value(row.service_fee),
            decimal_value(row.jinying_amount), net_investment,
            row_occupation_weight, row_occupation_amount,
        ))

    hotel_groups: dict[tuple[str, str], list[HotelLedger]] = defaultdict(list)
    for row in hotel_rows:
        hotel_groups[hotel_period_key(row)].append(row)
        total_realized += decimal_value(row.jinying_amount)
        total_gross += decimal_value(row.service_fee)

    for (scenic_id, _), rows in hotel_groups.items():
        representative = max(rows, key=lambda item: decimal_value(item.payment_amount))
        payment = decimal_value(representative.payment_amount)
        co_investment = decimal_value(getattr(representative, "co_investment_amount", 0))
        net_investment = payment - co_investment
        total_invested += net_investment
        payment_date = next((row.payment_date for row in rows if row.payment_date), None)
        repay_date = next((row.repay_date for row in rows if row.repay_date), None)
        period_occupation_weight, period_occupation_amount = occupation_values(
            net_investment, payment_date, repay_date, today,
        )
        add_occupation(period_occupation_weight, period_occupation_amount)
        total_fee = sum((decimal_value(row.service_fee) for row in rows), _ZERO)
        realized = sum((decimal_value(row.jinying_amount) for row in rows), _ZERO)
        ledger_profit.append(_profit_point(
            scenic_id, "hotel", representative, total_fee, realized, net_investment,
            period_occupation_weight, period_occupation_amount,
        ))

    ledger_profit.sort(key=lambda item: (
        item["year"] is None, item["year"] or 9999, item["month"] or 99,
        item["period_key"], item["scenic_id"], item["business_type"],
    ))
    years = sorted(
        {item["year"] for item in ledger_profit if item["year"] is not None}, reverse=True
    )
    scenic_ids = sorted({row.scenic_id for row in [*ticket_rows, *hotel_rows]})
    occupation_days = (
        round(float(occupation_weight / occupation_amount), 1) if occupation_amount else None
    )
    return {
        "existing_scale": total_invested,
        "total_realized_scale": total_realized,
        "total_gross_income": total_gross,
        "capital_occupation_days": occupation_days,
        "ledger_profit": ledger_profit,
        "available_years": years,
        "scenic_ids": scenic_ids,
    }


def _within(row, requested_start: date, requested_end: date) -> bool:
    period = bounded_period_date(row)
    return period is not None and requested_start <= period <= requested_end


def _coverage(rows: Sequence) -> tuple[date | None, date | None, datetime | None]:
    starts: list[date] = []
    ends: list[date] = []
    updates: list[datetime] = []
    for row in rows:
        period = bounded_period_date(row)
        if period is None:
            continue
        start = getattr(row, "period_start", None) or period
        end = getattr(row, "period_end", None) or period
        starts.append(start.date() if isinstance(start, datetime) else start)
        ends.append(end.date() if isinstance(end, datetime) else end)
        updated = getattr(row, "updated_at", None)
        if isinstance(updated, datetime):
            updates.append(updated)
    return (
        min(starts) if starts else None,
        max(ends) if ends else None,
        max(updates) if updates else None,
    )


def _summary_for_scenic(
    scenic_id: str,
    ticket_rows: Sequence[TicketLedger],
    hotel_rows: Sequence[HotelLedger],
    requested_start: date,
    requested_end: date,
    scenic_name: str | None = None,
) -> ScenicSummary:
    rows = [*ticket_rows, *hotel_rows]
    metrics = build_financial_metrics(ticket_rows, hotel_rows, today=requested_end)
    writeoff_count = sum(int(getattr(row, "order_count", 0) or 0) for row in rows)
    positive_count = sum(int(getattr(row, "positive_count", 0) or 0) for row in rows)
    rate = (
        (Decimal(positive_count) / Decimal(writeoff_count) * _PERCENT).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ) if writeoff_count else Decimal("0.00")
    )
    covered_start, covered_end, updated_at = _coverage(rows)
    ticket_total = sum((decimal_value(row.jinying_amount) for row in ticket_rows), _ZERO)
    hotel_total = sum((decimal_value(row.jinying_amount) for row in hotel_rows), _ZERO)
    name = scenic_name or get_effective_config(None, scenic_id).scenic_name
    return ScenicSummary(
        scenic_id=scenic_id,
        scenic_name=name,
        requested_start=requested_start,
        requested_end=requested_end,
        covered_start=covered_start,
        covered_end=covered_end,
        data_updated_at=updated_at,
        partial_coverage=(
            covered_start is None or covered_end is None
            or covered_start > requested_start or covered_end < requested_end
        ),
        sales=metrics["total_realized_scale"],
        writeoff_count=writeoff_count,
        positive_count=positive_count,
        writeoff_rate=rate,
        existing_scale=metrics["existing_scale"],
        realized_scale=metrics["total_realized_scale"],
        gross_profit=metrics["total_gross_income"],
        capital_occupation_days=metrics["capital_occupation_days"],
        ticket_total=ticket_total,
        hotel_total=hotel_total,
    )


def aggregate_rows(
    ticket_rows: Sequence[TicketLedger],
    hotel_rows: Sequence[HotelLedger],
    requested_start: date,
    requested_end: date,
    *,
    scenic_ids: Sequence[str] | None = None,
    scenic_names: dict[str, str] | None = None,
) -> list[ScenicSummary]:
    tickets = [row for row in ticket_rows if _within(row, requested_start, requested_end)]
    hotels = [row for row in hotel_rows if _within(row, requested_start, requested_end)]
    ids = list(dict.fromkeys(scenic_ids or sorted({row.scenic_id for row in [*tickets, *hotels]})))
    names = scenic_names or {}
    return [
        _summary_for_scenic(
            scenic_id,
            [row for row in tickets if row.scenic_id == scenic_id],
            [row for row in hotels if row.scenic_id == scenic_id],
            requested_start,
            requested_end,
            names.get(scenic_id),
        )
        for scenic_id in ids
    ]


class ScenicAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _date_condition(model, date_range: DateRange):
        return or_(
            model.period_end.between(date_range.start, date_range.end),
            and_(
                model.period_end.is_(None),
                model.period_start.between(date_range.start, date_range.end),
            ),
        )

    def _load_bounded(self, scenic_ids: Sequence[str], date_range: DateRange):
        tickets = self.db.scalars(select(TicketLedger).where(
            TicketLedger.scenic_id.in_(scenic_ids),
            self._date_condition(TicketLedger, date_range),
        )).all()
        hotels = self.db.scalars(select(HotelLedger).where(
            HotelLedger.scenic_id.in_(scenic_ids),
            self._date_condition(HotelLedger, date_range),
        )).all()
        return tickets, hotels

    def _names(self, scenic_ids: Sequence[str]) -> dict[str, str]:
        return {
            scenic_id: get_effective_config(self.db, scenic_id).scenic_name
            for scenic_id in scenic_ids
        }

    def summary(self, scenic_ids: Sequence[str], date_range: DateRange) -> list[ScenicSummary]:
        ids = list(dict.fromkeys(scenic_ids))
        tickets, hotels = self._load_bounded(ids, date_range)
        return aggregate_rows(
            tickets, hotels, date_range.start, date_range.end,
            scenic_ids=ids, scenic_names=self._names(ids),
        )

    def summary_all(self, scenic_ids: Sequence[str]) -> list[ScenicSummary]:
        ids = list(dict.fromkeys(scenic_ids))
        tickets = self.db.scalars(
            select(TicketLedger).where(TicketLedger.scenic_id.in_(ids))
        ).all()
        hotels = self.db.scalars(
            select(HotelLedger).where(HotelLedger.scenic_id.in_(ids))
        ).all()
        dated = [bounded_period_date(row) for row in [*tickets, *hotels]]
        dated = [value for value in dated if value is not None]
        today = date.today()
        start, end = (min(dated), max(dated)) if dated else (today, today)
        names = self._names(ids)
        return [
            _summary_for_scenic(
                scenic_id,
                [row for row in tickets if row.scenic_id == scenic_id],
                [row for row in hotels if row.scenic_id == scenic_id],
                start, end, names.get(scenic_id),
            )
            for scenic_id in ids
        ]

    def trend(
        self,
        scenic_ids: Sequence[str],
        date_range: DateRange,
        dimension: Literal["month", "platform"],
    ) -> list[ScenicTrendPoint]:
        if dimension not in {"month", "platform"}:
            raise ValueError("趋势维度仅支持 month 或 platform")
        ids = list(dict.fromkeys(scenic_ids))
        tickets, hotels = self._load_bounded(ids, date_range)
        names = self._names(ids)
        buckets: dict[tuple[str, str], tuple[list[TicketLedger], list[HotelLedger]]] = {}

        for business_type, rows in (("ticket", tickets), ("hotel", hotels)):
            for row in rows:
                if dimension == "month":
                    period = bounded_period_date(row)
                    if period is None:
                        continue
                    key = period.strftime("%Y-%m")
                else:
                    key = (getattr(row, "platform", "") or "未标注").strip()
                ticket_bucket, hotel_bucket = buckets.setdefault((row.scenic_id, key), ([], []))
                (ticket_bucket if business_type == "ticket" else hotel_bucket).append(row)

        points: list[ScenicTrendPoint] = []
        for (scenic_id, key), (ticket_bucket, hotel_bucket) in sorted(buckets.items()):
            if dimension == "month":
                year, month = (int(value) for value in key.split("-"))
                bucket_start = max(date(year, month, 1), date_range.start)
                next_month = date(year + (month == 12), month % 12 + 1, 1)
                bucket_end = min(next_month - timedelta(days=1), date_range.end)
                label = f"{year}年{month}月"
            else:
                bucket_start, bucket_end, label = date_range.start, date_range.end, key
            summary = _summary_for_scenic(
                scenic_id, ticket_bucket, hotel_bucket, bucket_start, bucket_end,
                names.get(scenic_id),
            )
            points.append(ScenicTrendPoint(
                scenic_id=scenic_id,
                scenic_name=summary.scenic_name,
                dimension=dimension,
                key=key,
                label=label,
                requested_start=summary.requested_start,
                requested_end=summary.requested_end,
                covered_start=summary.covered_start,
                covered_end=summary.covered_end,
                data_updated_at=summary.data_updated_at,
                partial_coverage=summary.partial_coverage,
                sales=summary.sales,
                writeoff_count=summary.writeoff_count,
                positive_count=summary.positive_count,
                writeoff_rate=summary.writeoff_rate,
                gross_profit=summary.gross_profit,
            ))
        return points
