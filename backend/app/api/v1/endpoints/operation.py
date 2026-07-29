"""经营数据端点（可视化看板）。

权限：STAFF / LEADER 可查看看板；录入数据仅 LEADER。
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.enums import ContractStatus, DIRECTOR_ROLES, FINANCE_ROLES, InvoiceStatus, Role

# 经营数据查看：全部非法律顾问 + 超管（这些接口 首页战略总览/大屏 也在用，故不能再排除法务风控）
_view_guard = require_roles(
    Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.RISK_AUDITOR, *FINANCE_ROLES, *DIRECTOR_ROLES,
)
from app.db.session import get_db
from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.operation import OperationData
from app.models.project import ProjectMetrics
from app.schemas.common import Response
from app.schemas.financial import FinancialDashboard
from app.schemas.operation import (
    DashboardData,
    KpiSummary,
    LineShare,
    OperationDataCreate,
    OperationDataOut,
    TrendPoint,
)
from app.services.ai_agent import diagnose as ai_diagnose_service
from app.services import financial as financial_svc

router = APIRouter()


@router.get(
    "/dashboard",
    response_model=Response[DashboardData],
    summary="经营数据看板聚合",
    dependencies=[Depends(_view_guard)],
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
    dependencies=[Depends(_view_guard)],
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


@router.get(
    "/ai-diagnose",
    response_model=Response[dict],
    summary="AI 智能大脑：业务/财务风险诊断与资金投资建议",
    dependencies=[Depends(_view_guard)],
)
def ai_diagnose(year: int = Query(2026), db: Session = Depends(get_db)):
    """聚合真实经营/发票/合同数据，作为 Context 交由 AI 智能体（DeepSeek）产出风险预警与
    闲置资金投资建议；未配置大模型时自动回退内置规则引擎。"""
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

    metrics = {
        "revenue": revenue, "cost": cost, "profit": profit, "margin": round(margin, 1),
        "orders": orders, "idle_funds": idle,
        "pending_invoice": pending_invoice, "pending_contracts": pending_contracts,
    }
    return Response.ok(ai_diagnose_service(metrics))


# --------------------------------------------------------------------------- #
# 文旅台账经营指标
# --------------------------------------------------------------------------- #
@router.get(
    "/financial",
    response_model=Response[FinancialDashboard],
    summary="经营核心指标与台账服务费图表",
    dependencies=[Depends(_view_guard)],
)
def financial_dashboard(db: Session = Depends(get_db)):
    """返回台账净投入、销售额、毛利润、占用时长及逐期服务费，供经营页与大屏共用。"""
    return Response.ok(financial_svc.build_dashboard(db))


@router.get(
    "/projects/geo",
    response_model=Response[dict],
    summary="大屏地图点位（项目→城市，数据驱动）",
    dependencies=[Depends(_view_guard)],
)
def projects_geo(
    hub: str = Query("山东省", description="中枢省(飞线汇聚点)"),
    db: Session = Depends(get_db),
):
    """按城市聚合 biz_project_metrics 的已入库项目，返回大屏地图所需的动态点位。

    - 城市/经纬度由上传时从项目名自动解析并入库（见 services/geo_gazetteer.py）。
    - `version` 为廉价数据指纹（项目数 + 投入合计），前端轮询到它变化即刷新地图，
      实现「上传即上屏」。
    """
    rows = db.scalars(
        select(ProjectMetrics).where(ProjectMetrics.lng.isnot(None))
    ).all()

    # 按城市聚合（同城多项目合并点位，金额相加、项目名收集）。
    by_city: dict[str, dict] = {}
    for r in rows:
        key = r.city or r.province or r.project_name
        agg = by_city.get(key)
        if agg is None:
            agg = {
                "city": r.city or key,
                "province": r.province or "",
                "coord": [float(r.lng), float(r.lat)],
                "invested": 0.0,
                "realized": 0.0,
                "gross_profit": 0.0,
                "projects": [],
            }
            by_city[key] = agg
        agg["invested"] += float(r.invested_amount or 0)
        agg["realized"] += float(r.realized_scale or 0)
        agg["gross_profit"] += float(r.gross_profit or 0)
        agg["projects"].append(r.project_name)

    points = []
    for agg in by_city.values():
        # value 作为点位/飞线强度基准 = 投入金额（现存业务规模）。
        agg["value"] = round(agg["invested"], 2)
        points.append(agg)
    points.sort(key=lambda p: p["value"], reverse=True)

    total = db.execute(
        select(
            func.count(ProjectMetrics.id),
            func.coalesce(func.sum(ProjectMetrics.invested_amount), 0),
        )
    ).one()
    matched = len(rows)
    unmatched = int(total[0]) - matched  # 已入库但未解析出城市的项目数

    return Response.ok({
        "hub": hub,
        "points": points,
        "matched": matched,
        "unmatched": unmatched,
        # 数据指纹：项目总数 + 投入合计（整数分），任一变化即触发前端刷新。
        "version": f"{int(total[0])}-{int(Decimal(str(total[1])) * 100)}",
    })
