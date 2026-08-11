"""Historical repair planning for affected ticket-ledger rows."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.models.ticket_ledger import TicketLedger
from app.services import ticket_ledger as tl_svc


MONEY_TOLERANCE = Decimal("0.005")
MONEY_QUANTUM = Decimal("0.01")
TARGETS = frozenset({
    ("zunyi-zoo", "抖音"),
    ("zunyi-zoo", "同程"),
    ("fuzhou-ouleb", "抖音"),
})

CALCULATED_FIELDS = (
    "supplier_received",
    "supplier_commission",
    "publisher_due",
    "hexiao_amount",
    "jinying_amount",
    "service_fee",
    "daily_json",
    "order_count",
    "positive_count",
)
MONEY_FIELDS = frozenset({
    "supplier_received",
    "supplier_commission",
    "publisher_due",
    "hexiao_amount",
    "jinying_amount",
    "service_fee",
})
REPORT_FIELDS = (
    "supplier_received",
    "supplier_commission",
    "publisher_due",
    "hexiao_amount",
    "jinying_amount",
    "service_fee",
    "order_count",
    "positive_count",
)


@dataclass(frozen=True)
class RepairPlanItem:
    row: TicketLedger
    before: dict[str, Any]
    after: dict[str, Any]
    protected_supplier_received: bool
    protected_commission: bool
    protected_hexiao: bool
    protected_jinying: bool


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid money value: {value!r}") from exc


def _money(value: Any) -> Decimal:
    return _decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _money_equal(left: Any, right: Any) -> bool:
    return abs(_decimal(left) - _decimal(right)) <= MONEY_TOLERANCE


def _snapshot_received(daily_json: str) -> Decimal:
    try:
        days = json.loads(daily_json)
    except (TypeError, ValueError) as exc:
        raise ValueError("stored daily_json is not valid JSON") from exc
    if not isinstance(days, list):
        raise ValueError("stored daily_json must be a JSON list")

    total = Decimal("0")
    for index, day in enumerate(days):
        if not isinstance(day, Mapping):
            raise ValueError(f"stored daily_json item {index} must be an object")
        try:
            total += Decimal(str(day.get("r", 0) or 0))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(
                f"stored daily_json item {index} has invalid receipt"
            ) from exc
    return total


def _row_rate(row: TicketLedger, field: str, default: Decimal) -> Decimal:
    value = getattr(row, field)
    return default if value is None else value


def _recompute(
    row: TicketLedger,
    daily_json: str,
    commission_override: Decimal | None = None,
) -> dict[str, Decimal]:
    result = tl_svc.recompute_from_json(
        daily_json,
        _row_rate(row, "rate_hexiao", tl_svc.DEFAULT_RATE_HEXIAO),
        _row_rate(row, "rate_settle", tl_svc.DEFAULT_RATE_SETTLE),
        commission_override,
        _row_rate(row, "commission_rate", tl_svc.DEFAULT_COMMISSION_RATE),
        row.platform or "抖音",
        scenic_id=row.scenic_id,
    )
    if result is None:
        raise ValueError(f"row {row.id} has no calculable daily snapshot")
    return result


def _period_calculation(
    row: TicketLedger,
    publisher_due: Decimal,
) -> dict[str, Decimal]:
    rate_hexiao = _row_rate(row, "rate_hexiao", tl_svc.DEFAULT_RATE_HEXIAO)
    rate_settle = _row_rate(row, "rate_settle", tl_svc.DEFAULT_RATE_SETTLE)
    hexiao_amount = _money(publisher_due * rate_hexiao)
    jinying_amount = _money(publisher_due * rate_settle)
    return {
        "hexiao_amount": hexiao_amount,
        "jinying_amount": jinying_amount,
    }


def plan_repair_row(
    row: TicketLedger,
    platform_info: Mapping[str, Any],
) -> RepairPlanItem:
    """Return a repair decision without assigning any ORM attribute."""
    if platform_info.get("platform") != row.platform:
        raise ValueError(
            f"row {row.id} platform mismatch: {row.platform!r} != "
            f"{platform_info.get('platform')!r}"
        )

    old_received = _snapshot_received(row.daily_json or "")
    old_calc = _recompute(row, row.daily_json or "")
    protected_supplier_received = not _money_equal(
        row.supplier_received, old_received
    )
    protected_commission = not _money_equal(
        row.supplier_commission, old_calc["supplier_commission"]
    )
    protected_hexiao = not _money_equal(
        row.hexiao_amount, old_calc["hexiao_amount"]
    )
    protected_jinying = not _money_equal(
        row.jinying_amount, old_calc["jinying_amount"]
    )

    new_daily_json = str(platform_info["daily_json"])
    new_calc = _recompute(row, new_daily_json)
    supplier_received = _money(
        row.supplier_received
        if protected_supplier_received
        else platform_info["supplier_received"]
    )
    supplier_commission = _money(
        row.supplier_commission
        if protected_commission
        else new_calc["supplier_commission"]
    )
    publisher_due = _money(supplier_received - supplier_commission)

    selected_calc = new_calc
    downstream_is_automatic = not (protected_hexiao and protected_jinying)
    if protected_commission and downstream_is_automatic:
        if row.platform == "抖音":
            selected_calc = _recompute(row, new_daily_json, supplier_commission)
        else:
            selected_calc = _period_calculation(row, publisher_due)
    if protected_supplier_received and downstream_is_automatic:
        selected_calc = _period_calculation(row, publisher_due)

    hexiao_amount = _money(
        row.hexiao_amount
        if protected_hexiao
        else selected_calc["hexiao_amount"]
    )
    jinying_amount = _money(
        row.jinying_amount
        if protected_jinying
        else selected_calc["jinying_amount"]
    )
    before = {field: getattr(row, field) for field in CALCULATED_FIELDS}
    after = {
        "supplier_received": supplier_received,
        "supplier_commission": supplier_commission,
        "publisher_due": publisher_due,
        "hexiao_amount": hexiao_amount,
        "jinying_amount": jinying_amount,
        "service_fee": _money(jinying_amount - hexiao_amount),
        "daily_json": new_daily_json,
        "order_count": int(platform_info["order_count"] or 0),
        "positive_count": int(platform_info["positive_count"] or 0),
    }
    return RepairPlanItem(
        row=row,
        before=before,
        after=after,
        protected_supplier_received=protected_supplier_received,
        protected_commission=protected_commission,
        protected_hexiao=protected_hexiao,
        protected_jinying=protected_jinying,
    )


def _target_rows(db: Session) -> list[TicketLedger]:
    return db.scalars(
        select(TicketLedger)
        .where(
            tuple_(TicketLedger.scenic_id, TicketLedger.platform).in_(list(TARGETS))
        )
        .order_by(
            TicketLedger.scenic_id.asc(),
            TicketLedger.period_start.is_(None),
            TicketLedger.period_start.asc(),
            TicketLedger.row_no.asc(),
            TicketLedger.id.asc(),
        )
    ).all()


def _source_path(upload_root: Path, row: TicketLedger) -> Path:
    stored = row.detail_stored or ""
    if not stored or Path(stored).name != stored:
        raise ValueError(
            f"row {row.id} detail_stored must be a non-empty basename: {stored!r}"
        )
    source = upload_root / f"ticket_detail_{row.scenic_id}" / stored
    if not source.is_file():
        raise ValueError(f"row {row.id} source file does not exist: {source}")
    return source


def build_repair_plan(
    db: Session,
    upload_root: Path,
) -> list[RepairPlanItem]:
    """Validate and parse every target source before returning a pure plan."""
    rows = _target_rows(db)
    grouped: dict[tuple[str, str], list[TicketLedger]] = defaultdict(list)
    for row in rows:
        grouped[(row.scenic_id, row.detail_stored or "")].append(row)

    sources: dict[tuple[str, str], Path] = {}
    for key, group in grouped.items():
        sources[key] = _source_path(Path(upload_root), group[0])

    items: list[RepairPlanItem] = []
    for key, group in grouped.items():
        representative = group[0]
        source = sources[key]
        parsed = tl_svc.parse_reconciliation(
            source.read_bytes(),
            filename=(
                representative.detail_name
                or representative.source_file
                or representative.detail_stored
            ),
            scenic_id=representative.scenic_id,
            rate_hexiao=_row_rate(
                representative, "rate_hexiao", tl_svc.DEFAULT_RATE_HEXIAO
            ),
            rate_settle=_row_rate(
                representative, "rate_settle", tl_svc.DEFAULT_RATE_SETTLE
            ),
            commission_rate=_row_rate(
                representative,
                "commission_rate",
                tl_svc.DEFAULT_COMMISSION_RATE,
            ),
            commission_override=None,
            ticket_product=(
                representative.ticket_product or tl_svc.DEFAULT_TICKET_PRODUCT
            ),
        )
        platform_infos = parsed.get("platforms", [])
        for row in group:
            matches = [
                info for info in platform_infos if info.get("platform") == row.platform
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"row {row.id} requires exactly one parsed {row.platform!r} "
                    f"platform result, found {len(matches)}"
                )
            items.append(plan_repair_row(row, matches[0]))
    return items


def _period_key(row: TicketLedger) -> str:
    return (
        row.source_file
        or row.detail_name
        or row.period_text
        or row.check_date_text
        or "NA"
    )


def _load_scenic_rows(db: Session, scenic_id: str) -> list[TicketLedger]:
    return db.scalars(
        select(TicketLedger)
        .where(TicketLedger.scenic_id == scenic_id)
        .order_by(
            TicketLedger.period_start.is_(None),
            TicketLedger.period_start.asc(),
            TicketLedger.row_no.asc(),
            TicketLedger.id.asc(),
        )
    ).all()


def apply_repair_plan(
    db: Session,
    items: Sequence[RepairPlanItem],
) -> None:
    """Apply a validated plan and balances without owning the transaction."""
    if not items:
        return
    for item in items:
        for field, value in item.after.items():
            setattr(item.row, field, value)
    db.flush()

    for scenic_id in dict.fromkeys(item.row.scenic_id for item in items):
        rows = _load_scenic_rows(db, scenic_id)
        balances = tl_svc.calculate_running_balances(
            scenic_id, rows, group_by=_period_key
        )
        for row, balance in zip(rows, balances):
            row.pending_writeoff = balance


def _field_changed(field: str, before: Any, after: Any) -> bool:
    if field in MONEY_FIELDS:
        return not _money_equal(before, after)
    return before != after


def _format_value(field: str, value: Any) -> str:
    if field in MONEY_FIELDS:
        return f"{_money(value):.2f}"
    return str(value)


def format_repair_plan(items: Sequence[RepairPlanItem]) -> str:
    lines: list[str] = []
    for item in items:
        row = item.row
        lines.append(
            f"row={row.id} scenic={row.scenic_id} platform={row.platform} "
            f"period={row.period_text or row.check_date_text or 'NA'}"
        )
        for field in REPORT_FIELDS:
            before = item.before[field]
            after = item.after[field]
            if _field_changed(field, before, after):
                lines.append(
                    f"  {field}: {_format_value(field, before)} -> "
                    f"{_format_value(field, after)}"
                )
        protected = []
        if item.protected_supplier_received:
            protected.append("supplier_received")
        if item.protected_commission:
            protected.append("commission")
        if item.protected_hexiao:
            protected.append("hexiao")
        if item.protected_jinying:
            protected.append("jinying")
        lines.append(f"  protected: {', '.join(protected) if protected else 'none'}")
    return "\n".join(lines)
