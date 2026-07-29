"""经营数据中心的文旅台账聚合服务。

所有指标和图表数据只读取景区门票、酒店台账快照；不访问独立项目统计、
平台对账单或手工资金配置，也不重新执行台账业务计算。
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger


_LEDGER_DATE_RE = re.compile(r"(20\d{2})\D{0,3}(\d{1,2})(?:\D{0,3}(\d{1,2}))?")


def _decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def _period_date(row) -> date | None:
    """取台账归属期日期，缺少结构化日期时再从期次文本中兜底解析。"""
    for value in (getattr(row, "period_start", None), getattr(row, "period_end", None)):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
    text = getattr(row, "period_text", "") or getattr(row, "check_date_text", "") or ""
    match = _LEDGER_DATE_RE.search(text)
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


def _profit_point(scenic_id: str, business_type: str, row, service_fee: Decimal) -> dict:
    period_date = _period_date(row)
    period = _period_label(row)
    date_key = period_date.isoformat() if period_date else "undated"
    return {
        "scenic_id": scenic_id,
        "business_type": business_type,
        "period": period,
        "period_key": f"{date_key}::{period}",
        "year": period_date.year if period_date else None,
        "month": period_date.month if period_date else None,
        "service_fee": service_fee,
    }


def _hotel_period_key(row) -> tuple[str, str]:
    period = (
        getattr(row, "source_file", "")
        or getattr(row, "detail_name", "")
        or getattr(row, "period_text", "")
        or getattr(row, "check_date_text", "")
        or f"row:{getattr(row, 'id', '')}"
    )
    return row.scenic_id, period


def build_ledger_metrics(
    ticket_rows: list[TicketLedger],
    hotel_rows: list[HotelLedger],
    *,
    today: date | None = None,
) -> dict:
    """按台账快照计算经营指标；不回写台账，也不重新执行计算算法。"""
    today = today or date.today()
    total_invested = Decimal("0")
    total_realized = Decimal("0")
    total_gross = Decimal("0")
    occupation_weight = Decimal("0")
    occupation_amount = Decimal("0")
    ledger_profit: list[dict] = []

    def add_occupation(net_investment: Decimal, start: date | None, end: date | None) -> None:
        nonlocal occupation_weight, occupation_amount
        if net_investment <= 0 or not start:
            return
        finish = end or today
        days = max((finish - start).days, 0)
        occupation_weight += net_investment * Decimal(days)
        occupation_amount += net_investment

    for row in ticket_rows:
        payment = _decimal(row.payment_amount)
        co_investment = _decimal(getattr(row, "co_investment_amount", 0))
        net_investment = payment - co_investment
        total_invested += net_investment
        total_realized += _decimal(row.jinying_amount)
        total_gross += _decimal(row.service_fee)
        add_occupation(net_investment, row.pay_date, row.repay_date)
        ledger_profit.append(
            _profit_point(row.scenic_id, "ticket", row, _decimal(row.service_fee))
        )

    hotel_groups: dict[tuple[str, str], list[HotelLedger]] = defaultdict(list)
    for row in hotel_rows:
        hotel_groups[_hotel_period_key(row)].append(row)
        total_realized += _decimal(row.jinying_amount)
        total_gross += _decimal(row.service_fee)

    for (scenic_id, _), rows in hotel_groups.items():
        # 酒店同期多平台共享付款与跟投，只计算一次；销售额、服务费仍逐平台累计。
        representative = max(rows, key=lambda item: _decimal(item.payment_amount))
        payment = _decimal(representative.payment_amount)
        co_investment = _decimal(getattr(representative, "co_investment_amount", 0))
        net_investment = payment - co_investment
        total_invested += net_investment
        payment_date = next((row.payment_date for row in rows if row.payment_date), None)
        repay_date = next((row.repay_date for row in rows if row.repay_date), None)
        add_occupation(net_investment, payment_date, repay_date)
        total_fee = sum((_decimal(row.service_fee) for row in rows), Decimal("0"))
        ledger_profit.append(_profit_point(scenic_id, "hotel", representative, total_fee))

    ledger_profit.sort(
        key=lambda item: (
            item["year"] is None,
            item["year"] or 9999,
            item["month"] or 99,
            item["period_key"],
            item["scenic_id"],
            item["business_type"],
        )
    )
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


def build_dashboard(db: Session) -> dict:
    """只读取文旅门票、酒店台账，构建经营数据中心响应。"""
    ticket_rows = db.scalars(
        select(TicketLedger).order_by(TicketLedger.period_start, TicketLedger.id)
    ).all()
    hotel_rows = db.scalars(
        select(HotelLedger).order_by(HotelLedger.period_start, HotelLedger.id)
    ).all()
    return build_ledger_metrics(ticket_rows, hotel_rows)
