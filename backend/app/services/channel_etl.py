"""渠道回传数据 → 经营数据表（biz_operation_data）ETL。

按渠道配置的列映射解析表格，聚合到 (年, 月)，以「该渠道专属业务条线」覆盖式写入经营表，
从而联动首页看板与数据大屏的营收/利润图表。

覆盖式语义：每次汇入前先清除该业务条线的历史数据，再写入本次聚合结果，
保证同一渠道重复回传不会重复累加（幂等）。不同渠道使用不同 business_line 天然隔离。
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.operation import OperationData


def _to_decimal(cell) -> Decimal:
    """将单元格转为金额：去除 ¥、逗号、空格等。"""
    s = re.sub(r"[^\d.\-]", "", str(cell or "").strip())
    if not s or s in ("-", "."):
        return Decimal("0")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")


def _to_int(cell) -> int:
    try:
        return int(_to_decimal(cell))
    except (ValueError, InvalidOperation):
        return 0


def _parse_year_month(cell) -> tuple[int, int]:
    """从日期字符串中解析 (年, 月)，支持 2026-06 / 2026/6/1 / 2026年6月 等。"""
    nums = re.findall(r"\d+", str(cell or ""))
    if len(nums) < 2:
        raise ValueError(f"无法解析日期：{cell!r}")
    year = int(nums[0])
    month = int(nums[1])
    if not (1 <= month <= 12) or year < 1900:
        raise ValueError(f"年月超出范围：{cell!r}")
    return year, month


def sync_channel_to_operation(
    db: Session,
    channel: Channel,
    columns: list[str],
    rows: list[list],
    mapping: dict | None,
) -> dict:
    """执行 ETL；返回结果摘要 dict（对应 schemas.channel.SyncResult）。"""
    result = {
        "synced": False, "reason": "", "business_line": "",
        "months": 0, "rows_used": 0, "rows_skipped": 0, "total_revenue": 0.0,
    }

    if not mapping:
        result["reason"] = "未配置列映射，已保存原始数据但未汇入经营看板。"
        return result

    business_line = (mapping.get("business_line") or channel.name or "").strip()
    date_col = (mapping.get("date_col") or "").strip()
    revenue_col = (mapping.get("revenue_col") or "").strip()
    cost_col = (mapping.get("cost_col") or "").strip()
    order_col = (mapping.get("order_col") or "").strip()
    result["business_line"] = business_line

    if not date_col or not revenue_col:
        result["reason"] = "需至少指定「日期列」和「营收列」才能汇入经营看板。"
        return result

    col_idx = {c: i for i, c in enumerate(columns or [])}
    if date_col not in col_idx or revenue_col not in col_idx:
        result["reason"] = "映射的列名在当前表头中不存在，请重新选择。"
        return result

    buckets: dict[tuple[int, int], dict] = {}
    used = skipped = 0
    for row in rows or []:
        try:
            year, month = _parse_year_month(row[col_idx[date_col]])
            rev = _to_decimal(row[col_idx[revenue_col]])
        except (ValueError, IndexError, KeyError):
            skipped += 1
            continue
        cost = _to_decimal(row[col_idx[cost_col]]) if cost_col in col_idx else Decimal("0")
        orders = _to_int(row[col_idx[order_col]]) if order_col in col_idx else 0

        b = buckets.setdefault((year, month), {"revenue": Decimal("0"), "cost": Decimal("0"), "orders": 0})
        b["revenue"] += rev
        b["cost"] += cost
        b["orders"] += orders
        used += 1

    if not buckets:
        result["reason"] = "没有可解析的有效数据行（请检查日期/金额格式）。"
        result["rows_skipped"] = skipped
        return result

    # 覆盖式：清除该业务条线涉及年份的旧记录，再写入本次聚合
    years = {y for (y, _m) in buckets}
    db.execute(
        delete(OperationData).where(
            OperationData.business_line == business_line,
            OperationData.year.in_(years),
        )
    )
    total_revenue = Decimal("0")
    for (year, month), v in buckets.items():
        db.add(
            OperationData(
                year=year,
                month=month,
                business_line=business_line,
                revenue=v["revenue"],
                cost=v["cost"],
                profit=v["revenue"] - v["cost"],
                order_count=v["orders"],
            )
        )
        total_revenue += v["revenue"]
    db.commit()

    result.update({
        "synced": True,
        "reason": f"已将 {used} 行数据按业务条线「{business_line}」汇入经营看板（{len(buckets)} 个月）。",
        "months": len(buckets),
        "rows_used": used,
        "rows_skipped": skipped,
        "total_revenue": float(total_revenue),
    })
    return result
