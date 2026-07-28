"""景区台账通用纯函数计算引擎。

Excel 解析器负责把不同平台的明细归一为逐日数据；本模块只处理
费率、佣金、精度和期次递推，不访问数据库、不修改 ORM 对象。调用方
通过 ``scenic_id`` 保持数据作用域，并自行读取/持久化历史期次余额。
"""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Iterable, Mapping

CENT = Decimal("0.01")
DEFAULT_RATE_HEXIAO = Decimal("0.90")
DEFAULT_RATE_SETTLE = Decimal("0.94")
DEFAULT_FEE_PER_NIGHT = Decimal("44.00")
DEFAULT_COMMISSION_RATE = Decimal("0.06")


def quantize_money(value: Decimal | int | float | None) -> Decimal:
    """统一按业务规则四舍五入到分。"""
    return (value or Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)


def _require_scenic_id(scenic_id: str) -> str:
    sid = (scenic_id or "").strip()
    if not sid or len(sid) > 64:
        raise ValueError("scenic_id is required and must be at most 64 characters")
    return sid


def _as_days(excel_data) -> list[dict]:
    """接收解析器输出的 daily_json、逐日列表或 ``{"daily_json": ...}``。"""
    if isinstance(excel_data, Mapping):
        excel_data = excel_data.get("daily_json") or excel_data.get("daily")
    if isinstance(excel_data, str):
        try:
            excel_data = json.loads(excel_data)
        except (TypeError, ValueError):
            return []
    if not excel_data:
        return []
    return [dict(day) for day in excel_data]


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:  # noqa: BLE001
        return Decimal("0")


def _distribute_commission(days: list[dict], commission_override, commission_rate: Decimal):
    rate = commission_rate if commission_rate is not None else DEFAULT_COMMISSION_RATE
    auto = [quantize_money(
        _dec(d.get("shishou", d.get("s", 0))) * rate
        + _dec(d.get("daren", d.get("d", 0)))
        + _dec(d.get("tuanzhang", d.get("t", 0)))
    ) for d in days]
    total = quantize_money(sum(auto, Decimal("0")))
    if commission_override is None or abs(_dec(commission_override) - total) < Decimal("0.005"):
        return auto, total

    delta = _dec(commission_override) - total
    received_total = sum((_dec(d.get("shishou", d.get("s", 0))) for d in days), Decimal("0"))
    count = len(days) or 1
    adjusted = []
    for item, day in zip(auto, days):
        received = _dec(day.get("shishou", day.get("s", 0)))
        share = received / received_total if received_total > 0 else Decimal("1") / count
        adjusted.append(quantize_money(item + delta * share))
    return adjusted, quantize_money(commission_override)


def calculate_ticket_ledger(
    scenic_id: str,
    excel_data,
    *,
    supplier_received: Decimal | None = None,
    rate_hexiao: Decimal = DEFAULT_RATE_HEXIAO,
    rate_settle: Decimal = DEFAULT_RATE_SETTLE,
    commission_override=None,
    commission_rate: Decimal = DEFAULT_COMMISSION_RATE,
    platform: str = "抖音",
) -> dict | None:
    """计算一个景区的一期门票台账。

    ``excel_data`` 是门票解析器产生的逐日快照，而不是数据库对象；因此
    同一函数可用于上传预览、保存和编辑。历史余额由调用方按 scenic_id
    读取后使用 :func:`calculate_running_balances` 递推。
    """
    sid = _require_scenic_id(scenic_id)
    days = _as_days(excel_data)
    if not days:
        if supplier_received is None:
            return None
        commission = _dec(commission_override)
        if platform != "抖音":
            commission = Decimal("0")
        base = _dec(supplier_received) - commission
        hexiao = quantize_money(base * (rate_hexiao or Decimal("0")))
        settle = quantize_money(base * (rate_settle or Decimal("0")))
        return {
            "scenic_id": sid,
            "supplier_commission": quantize_money(commission),
            "publisher_due": quantize_money(base),
            "hexiao_amount": hexiao,
            "service_fee": quantize_money(settle - hexiao),
            "jinying_amount": settle,
        }
    is_douyin = platform == "抖音"
    if is_douyin:
        commissions, commission_total = _distribute_commission(
            days, commission_override, commission_rate
        )
    else:
        commissions, commission_total = [Decimal("0")] * len(days), Decimal("0")

    publisher_due = hexiao = settle = Decimal("0")
    for day, commission in zip(days, commissions):
        received = _dec(day.get("received", day.get("recv", day.get("r", 0))))
        base = received - commission
        publisher_due += base
        hexiao += quantize_money(base * (rate_hexiao or Decimal("0")))
        settle += quantize_money(base * (rate_settle or Decimal("0")))
    return {
        "scenic_id": sid,
        "supplier_commission": quantize_money(commission_total),
        "publisher_due": quantize_money(publisher_due),
        "hexiao_amount": quantize_money(hexiao),
        "service_fee": quantize_money(settle - hexiao),
        "jinying_amount": quantize_money(settle),
    }


def calculate_hotel_ledger(
    scenic_id: str,
    excel_data,
    *,
    platform: str = "抖音",
    base_received: Decimal | None = None,
    rate_hexiao: Decimal = DEFAULT_RATE_HEXIAO,
    rate_settle: Decimal = DEFAULT_RATE_SETTLE,
    fee_per_night: Decimal = DEFAULT_FEE_PER_NIGHT,
    fee_algo: int = 1,
    commission_override=None,
    room_nights_override: int | None = None,
    commission_rate: Decimal = DEFAULT_COMMISSION_RATE,
) -> dict | None:
    """计算一个景区的一期酒店台账，支持算法1/2和多平台。"""
    sid = _require_scenic_id(scenic_id)
    days = _as_days(excel_data)
    if not days:
        if base_received is None:
            return None
        commission = _dec(commission_override)
        if platform != "抖音":
            commission = Decimal("0")
        settle_base = _dec(base_received) - commission
        hexiao = quantize_money(settle_base * (rate_hexiao or Decimal("0")))
        if int(fee_algo or 1) == 2:
            settle = quantize_money(settle_base * (rate_settle or Decimal("0")))
            fee = quantize_money(settle - hexiao)
        else:
            fee = quantize_money(Decimal(int(room_nights_override or 0)) * (fee_per_night or Decimal("0")))
            settle = quantize_money(hexiao + fee)
        return {
            "scenic_id": sid,
            "supplier_commission": quantize_money(commission),
            "settle_base": quantize_money(settle_base),
            "hexiao_amount": hexiao,
            "service_fee": fee,
            "jinying_amount": settle,
        }
    is_douyin = platform == "抖音"
    if is_douyin:
        commissions, commission_total = _distribute_commission(
            days, commission_override, commission_rate
        )
    else:
        commissions, commission_total = [Decimal("0")] * len(days), Decimal("0")

    settle_base = hexiao = settle = service_fee = Decimal("0")
    nights_total = 0
    for day, commission in zip(days, commissions):
        raw_base = (
            _dec(day.get("recv", day.get("r", 0)))
            if is_douyin
            else _dec(day.get("base", day.get("b", 0)))
        )
        base = raw_base - commission
        settle_base += base
        nights_total += int(day.get("nights", day.get("n", 0)) or 0)
        hx = quantize_money(base * (rate_hexiao or Decimal("0")))
        hexiao += hx
        if int(fee_algo or 1) == 2:
            jy = quantize_money(base * (rate_settle or Decimal("0")))
            settle += jy
            service_fee += quantize_money(jy - hx)
    if int(fee_algo or 1) != 2:
        nights = room_nights_override if room_nights_override is not None else nights_total
        service_fee = quantize_money(Decimal(int(nights or 0)) * (fee_per_night or Decimal("0")))
        settle = quantize_money(hexiao + service_fee)
    return {
        "scenic_id": sid,
        "supplier_commission": quantize_money(commission_total),
        "settle_base": quantize_money(settle_base),
        "hexiao_amount": quantize_money(hexiao),
        "service_fee": quantize_money(service_fee),
        "jinying_amount": quantize_money(settle),
    }


def running_pending(prev_balance: Decimal, payment_amount: Decimal, hexiao_amount: Decimal) -> Decimal:
    return quantize_money(_dec(prev_balance) + _dec(payment_amount) - _dec(hexiao_amount))


def calculate_running_balances(
    scenic_id: str,
    rows: Iterable,
    *,
    group_by: Callable[[object], object] | None = None,
) -> list[Decimal]:
    """按传入的历史期次顺序计算待核销余额，不修改 rows。

    门票一行就是一期；酒店可通过 ``group_by`` 将同一期的多个平台行
    聚合后递推，并把同一余额返回给该期的每个平台行。
    """
    _require_scenic_id(scenic_id)
    rows = list(rows)
    if not rows:
        return []
    if group_by is not None:
        groups: dict[object, list] = {}
        order: list[object] = []
        for row in rows:
            key = group_by(row)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(row)
        by_row: dict[int, Decimal] = {}
        previous = Decimal("0")
        for key in order:
            group = groups[key]
            payment = max((_dec(getattr(row, "payment_amount", 0)) for row in group), default=Decimal("0"))
            writeoff = sum((_dec(getattr(row, "hexiao_amount", 0)) for row in group), Decimal("0"))
            previous = running_pending(previous, payment, writeoff)
            for row in group:
                by_row[id(row)] = previous
        return [by_row[id(row)] for row in rows]
    previous = Decimal("0")
    balances = []
    for row in rows:
        previous = running_pending(
            previous,
            getattr(row, "payment_amount", 0),
            getattr(row, "hexiao_amount", 0),
        )
        balances.append(previous)
    return balances


# 兼容设计文档中的命名，同时保留 Python 项目既有 snake_case 风格。
calculateTicketLedger = calculate_ticket_ledger
calculateHotelLedger = calculate_hotel_ledger
