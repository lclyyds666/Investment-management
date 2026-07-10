"""财务对账单处理服务。

职责：
1. 解析多 Sheet 的平台对账单 xlsx（抖音/美团/携程），提取每平台的
   「出版应得到账金额」(已实现业务规模) 与「应扣出版预付」(已实现业务毛收入/回款)，
   并从明细 Sheet 统计订单数与间夜。
2. UPSERT 写入 biz_financial_metrics（按平台+账期覆盖，幂等）。
3. 汇总构建经营页 / 大屏共用的财务看板视图（含收益率、资金占用、可用资金）。
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from io import BytesIO

import openpyxl
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.financial import FinanceConfig, FinancialMetrics
from app.models.project import ProjectMetrics

PLATFORM_KEYWORDS = {
    "douyin": "抖音",
    "meituan": "美团",
    "ctrip": "携程",
}
PLATFORM_LABELS = {"douyin": "抖音", "meituan": "美团", "ctrip": "携程"}


def _num(v):
    """宽松地把单元格转为 Decimal（去除 ¥、逗号、空格等）；无法解析返回 None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return Decimal(str(v))
        except InvalidOperation:
            return None
    s = re.sub(r"[^\d.\-]", "", str(v).strip())
    if not s or s in ("-", "."):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _detect_platform(sheet_name: str):
    for key, kw in PLATFORM_KEYWORDS.items():
        if kw in sheet_name:
            return key
    return None


def _parse_period(title: str) -> str:
    """从对账单标题解析账期，如 '2026年6月24日-6月30日...' → '2026-06-24~06-30'。"""
    m = re.search(
        r"(\d{4})\D*?(\d{1,2})月(\d{1,2})日\s*[-~至到]\s*(?:(\d{1,2})月)?(\d{1,2})日",
        str(title or ""),
    )
    if not m:
        return ""
    y, m1, d1, m2, d2 = m.group(1), m.group(2), m.group(3), m.group(4) or m.group(2), m.group(5)
    return f"{y}-{int(m1):02d}-{int(d1):02d}~{int(m2):02d}-{int(d2):02d}"


def _parse_reconciliation(ws) -> dict | None:
    """从对账单 Sheet 提取 realized_scale / gross_income / period。

    对账单末尾有『总计』行，其数值列尾部形如 [..., 出版应得, 应扣预付, 应扣预付]
    （应扣预付在合并单元格中重复一次）。据此：
      gross_income  = 最后一个数值（应扣出版预付/回款）
      realized_scale= 倒数第三个数值（出版应得到账金额）
    """
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return None

    title = ""
    for c in rows[0]:
        if c is not None and str(c).strip():
            title = str(c)
            break
    period = _parse_period(title)

    total_row = None
    for r in rows:
        for c in r:
            if c is not None and str(c).strip() in ("总计", "合计"):
                total_row = r
                break
        if total_row is not None:
            break
    if total_row is None:
        return None

    nums = [x for x in (_num(c) for c in total_row) if x is not None]
    if len(nums) < 3:
        return None
    gross = nums[-1]
    realized = nums[-3]
    return {"realized_scale": realized, "gross_income": gross, "period": period}


def _parse_detail(ws) -> dict:
    """从明细 Sheet 统计 order_count / room_nights / gmv(可选)。"""
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"order_count": 0, "room_nights": 0, "gmv": None}

    header = [str(c).strip() if c is not None else "" for c in rows[0]]

    def find_col(*keywords):
        for i, h in enumerate(header):
            if all(k in h for k in keywords):
                return i
        return None

    ci_night = find_col("间夜")
    ci_gmv = find_col("订单实收")  # 抖音明细提供 GMV

    order_count = 0
    nights = Decimal("0")
    gmv = Decimal("0")
    has_gmv = ci_gmv is not None
    for r in rows[1:]:
        night = _num(r[ci_night]) if (ci_night is not None and ci_night < len(r)) else None
        if night is None:
            continue  # 跳过空行/小计行
        order_count += 1
        nights += night
        if has_gmv and ci_gmv < len(r):
            g = _num(r[ci_gmv])
            if g:
                gmv += g
    return {
        "order_count": order_count,
        "room_nights": int(nights),
        "gmv": (gmv if has_gmv else None),
    }


def parse_workbook(content: bytes) -> list[dict]:
    """解析对账单 xlsx，返回每平台一条指标 dict。"""
    wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    recon_ws, detail_ws = {}, {}
    for name in wb.sheetnames:
        plat = _detect_platform(name)
        if not plat:
            continue
        if "对账单" in name:
            recon_ws[plat] = wb[name]
        else:
            detail_ws[plat] = wb[name]

    results = []
    for plat, ws in recon_ws.items():
        base = _parse_reconciliation(ws)
        if not base:
            continue
        det = _parse_detail(detail_ws[plat]) if plat in detail_ws else {"order_count": 0, "room_nights": 0, "gmv": None}
        results.append({
            "platform": plat,
            "period": base["period"] or PLATFORM_LABELS.get(plat, plat),
            "realized_scale": base["realized_scale"],
            "gross_income": base["gross_income"],
            "gmv": det["gmv"],
            "order_count": det["order_count"],
            "room_nights": det["room_nights"],
        })
    return results


def upsert_metrics(db: Session, parsed: list[dict]) -> list[FinancialMetrics]:
    """按 (平台, 账期) UPSERT，覆盖式、幂等。"""
    saved = []
    for item in parsed:
        row = db.scalar(
            select(FinancialMetrics).where(
                FinancialMetrics.platform == item["platform"],
                FinancialMetrics.period == item["period"],
            )
        )
        if not row:
            row = FinancialMetrics(platform=item["platform"], period=item["period"])
            db.add(row)
        row.realized_scale = item["realized_scale"]
        row.gross_income = item["gross_income"]
        row.gmv = item["gmv"]
        row.order_count = item["order_count"]
        row.room_nights = item["room_nights"]
        saved.append(row)
    db.commit()
    for r in saved:
        db.refresh(r)
    return saved


def get_or_create_config(db: Session) -> FinanceConfig:
    cfg = db.scalar(select(FinanceConfig).limit(1))
    if not cfg:
        cfg = FinanceConfig(total_invested_cost=Decimal("0"))
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _to_platform_metric(row: FinancialMetrics) -> dict:
    return {
        "platform": row.platform,
        "platform_label": PLATFORM_LABELS.get(row.platform, row.platform),
        "period": row.period,
        "realized_scale": row.realized_scale,
        "gross_income": row.gross_income,
        "gmv": row.gmv,
        "order_count": row.order_count,
        "room_nights": row.room_nights,
    }


def _to_project_metric(row: ProjectMetrics) -> dict:
    return {
        "seq": row.seq,
        "project_name": row.project_name,
        "platforms": row.platforms,
        "invested_amount": row.invested_amount,
        "realized_scale": row.realized_scale,
        "gross_profit": row.gross_profit,
        "profit_rate": row.profit_rate,
        "pay_date": row.pay_date.isoformat() if row.pay_date else None,
        "term_months": row.term_months,
        "capital_occupied": (row.invested_amount or Decimal("0")) - (row.realized_scale or Decimal("0")),
    }


def build_dashboard(db: Session) -> dict:
    """构建财务经营看板聚合视图（项目维度驱动，经营页 & 大屏共用）。"""
    # —— 项目维度（Sheet2 驱动）——
    projects = db.scalars(select(ProjectMetrics).order_by(ProjectMetrics.seq)).all()
    total_invested = sum((p.invested_amount or Decimal("0") for p in projects), Decimal("0"))
    total_realized = sum((p.realized_scale or Decimal("0") for p in projects), Decimal("0"))
    total_gross = sum((p.gross_profit or Decimal("0") for p in projects), Decimal("0"))

    # 业务收益率 = 投入加权平均（仅统计有收益率的项目）
    rate_num = Decimal("0")
    rate_den = Decimal("0")
    for p in projects:
        if p.profit_rate is not None and p.invested_amount:
            rate_num += p.profit_rate * p.invested_amount
            rate_den += p.invested_amount
    profit_rate = float(rate_num / rate_den * 100) if rate_den else None

    capital_occupied = total_invested - total_realized  # 资金占用 = 投入 - 回款

    cfg = get_or_create_config(db)

    # —— 对账单平台明细（独立数据源，保留）——
    fm_rows = db.scalars(select(FinancialMetrics).order_by(FinancialMetrics.platform)).all()
    platforms = [_to_platform_metric(r) for r in fm_rows]

    return {
        "existing_scale": total_invested,           # 现存业务规模 = Σ投入(已投入本金)
        "total_realized_scale": total_realized,
        "total_gross_income": total_gross,
        "profit_rate": round(profit_rate, 2) if profit_rate is not None else None,
        "capital_occupied": capital_occupied,
        "available_funds": cfg.available_funds or Decimal("0"),
        "projects": [_to_project_metric(p) for p in projects],
        "invested_cost": cfg.total_invested_cost or Decimal("0"),
        "platforms": platforms,
    }
