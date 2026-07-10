"""经营数据端点（可视化看板）。

权限：STAFF / LEADER 可查看看板；录入数据仅 LEADER。
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.enums import ContractStatus, DIRECTOR_ROLES, InvoiceStatus
from app.db.session import get_db
from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.operation import OperationData
from app.schemas.common import Response
from app.schemas.operation import (
    DashboardData,
    KpiSummary,
    LineShare,
    OperationDataCreate,
    OperationDataOut,
    TrendPoint,
)

router = APIRouter()


@router.get(
    "/dashboard",
    response_model=Response[DashboardData],
    summary="经营数据看板聚合",
    dependencies=[Depends(get_current_user)],
)
def dashboard(
    year: int = Query(2026, description="统计年份"),
    db: Session = Depends(get_db),
):
    """返回三类聚合：KPI 汇总、按月趋势、按业务条线占比。"""
    base = select(OperationData).where(OperationData.year == year).subquery()

    # KPI 汇总
    kpi_row = db.execute(
        select(
            func.coalesce(func.sum(base.c.revenue), 0),
            func.coalesce(func.sum(base.c.cost), 0),
            func.coalesce(func.sum(base.c.profit), 0),
            func.coalesce(func.sum(base.c.order_count), 0),
        )
    ).one()
    kpi = KpiSummary(
        total_revenue=kpi_row[0],
        total_cost=kpi_row[1],
        total_profit=kpi_row[2],
        total_orders=kpi_row[3],
    )

    # 按月趋势
    trend_rows = db.execute(
        select(
            base.c.month,
            func.sum(base.c.revenue),
            func.sum(base.c.profit),
        )
        .group_by(base.c.month)
        .order_by(base.c.month)
    ).all()
    trend = [
        TrendPoint(month=f"{year}-{m:02d}", revenue=rev, profit=pro)
        for m, rev, pro in trend_rows
    ]

    # 按业务条线营收占比
    line_rows = db.execute(
        select(base.c.business_line, func.sum(base.c.revenue))
        .group_by(base.c.business_line)
        .order_by(func.sum(base.c.revenue).desc())
    ).all()
    line_share = [LineShare(business_line=name, revenue=rev) for name, rev in line_rows]

    return Response.ok(DashboardData(kpi=kpi, trend=trend, line_share=line_share))


@router.get(
    "",
    response_model=Response[list[OperationDataOut]],
    summary="经营数据明细列表",
    dependencies=[Depends(get_current_user)],
)
def list_operation(
    year: int = Query(2026),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(OperationData)
        .where(OperationData.year == year)
        .order_by(OperationData.month, OperationData.business_line)
    ).all()
    return Response.ok([OperationDataOut.model_validate(r) for r in rows])


@router.post(
    "",
    response_model=Response[OperationDataOut],
    summary="录入经营数据(公司负责人)",
    dependencies=[Depends(require_roles(*DIRECTOR_ROLES))],
)
def create_operation(
    payload: OperationDataCreate,
    db: Session = Depends(get_db),
):
    row = OperationData(**payload.model_dump())
    # profit 缺省时按 revenue-cost 计算
    if row.profit in (None, Decimal("0")):
        row.profit = row.revenue - row.cost
    db.add(row)
    db.commit()
    db.refresh(row)
    return Response.ok(OperationDataOut.model_validate(row))


def _yuan(v) -> str:
    return f"¥{float(v):,.0f}"


@router.get(
    "/ai-diagnose",
    response_model=Response[dict],
    summary="AI 智能大脑：业务/财务风险诊断与资金投资建议",
    dependencies=[Depends(get_current_user)],
)
def ai_diagnose(year: int = Query(2026), db: Session = Depends(get_db)):
    """基于真实经营/发票/合同数据聚合，输出风险预警与闲置资金投资建议（模拟 AI Agent）。"""
    agg = db.execute(
        select(
            func.coalesce(func.sum(OperationData.revenue), 0),
            func.coalesce(func.sum(OperationData.cost), 0),
            func.coalesce(func.sum(OperationData.profit), 0),
            func.coalesce(func.sum(OperationData.order_count), 0),
        ).where(OperationData.year == year)
    ).one()
    revenue, cost, profit, orders = (float(agg[0]), float(agg[1]), float(agg[2]), int(agg[3]))
    margin = (profit / revenue * 100) if revenue else 0.0

    invoices = db.scalars(select(Invoice)).all()
    pending_invoice = float(sum((i.amount for i in invoices if i.status == InvoiceStatus.PENDING), Decimal("0")))

    contracts = db.scalars(select(Contract)).all()
    pending_contracts = sum(1 for c in contracts if c.status == ContractStatus.PENDING)

    idle = round(profit * 0.6)  # 估算可动用于投资的闲置资金

    risks = []
    if margin < 30:
        risks.append({"level": "高", "title": "综合利润率偏低",
                      "detail": f"当前综合利润率约 {margin:.1f}%，低于健康线 30%，建议优化成本结构、聚焦高毛利业务线。"})
    else:
        risks.append({"level": "低", "title": "盈利能力稳健",
                      "detail": f"综合利润率约 {margin:.1f}%，处于健康区间，可适度扩张规模。"})
    if pending_invoice > 0:
        risks.append({"level": "中", "title": "应收/待开票资金占用",
                      "detail": f"待开票金额约 {_yuan(pending_invoice)}，存在资金回笼与税务确认风险，建议加快开票与回款节奏。"})
    if pending_contracts > 0:
        risks.append({"level": "中", "title": "合同审批积压",
                      "detail": f"有 {pending_contracts} 份合同处于 7 级审批流转中，建议关注审批时效，避免业务延误。"})

    suggestions = [
        {"title": "结构性存款配置",
         "detail": f"建议将约 {_yuan(round(idle * 0.5))} 配置为银行结构性存款，兼顾流动性与收益（预期年化 2.8%–3.2%）。"},
        {"title": "国债逆回购",
         "detail": f"月末/季末可将约 {_yuan(round(idle * 0.2))} 用于国债逆回购，捕捉短期利率高点，资金 T+1 可用。"},
        {"title": "供应链金融投放",
         "detail": f"依托核心供应商网络，将约 {_yuan(round(idle * 0.3))} 投入供应链票据/保理，提升资金周转与产业协同。"},
    ]

    summary = (
        f"本年度营收 {_yuan(revenue)}、利润 {_yuan(profit)}（利润率 {margin:.1f}%），"
        f"订单 {orders:,} 笔；结合应收与审批情况，估算当前可动用闲置资金约 {_yuan(idle)}。"
    )
    return Response.ok({
        "summary": summary,
        "metrics": {
            "revenue": revenue, "cost": cost, "profit": profit, "margin": round(margin, 1),
            "orders": orders, "idle_funds": idle,
            "pending_invoice": pending_invoice, "pending_contracts": pending_contracts,
        },
        "risks": risks,
        "suggestions": suggestions,
    })
