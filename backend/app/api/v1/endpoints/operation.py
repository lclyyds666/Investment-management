"""经营数据端点（可视化看板）。

权限：STAFF / LEADER 可查看看板；录入数据仅 LEADER。
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.enums import ContractStatus, DIRECTOR_ROLES, FINANCE_ROLES, InvoiceStatus
from app.db.session import get_db
from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.operation import OperationData
from app.schemas.common import Response
from app.schemas.financial import (
    AvailableFundsIn,
    FinancialDashboard,
    InvestedCostIn,
    ProjectUploadResult,
    UploadResult,
)
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
from app.services import project_etl

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


@router.get(
    "/ai-diagnose",
    response_model=Response[dict],
    summary="AI 智能大脑：业务/财务风险诊断与资金投资建议",
    dependencies=[Depends(get_current_user)],
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
# 财务经营指标（真实对账单回款数据）
# --------------------------------------------------------------------------- #
@router.get(
    "/financial",
    response_model=Response[FinancialDashboard],
    summary="财务经营指标看板（真实回款）",
    dependencies=[Depends(get_current_user)],
)
def financial_dashboard(db: Session = Depends(get_db)):
    """返回分平台已实现业务规模/毛收入 + 收益率/资金占用/可用资金聚合，供经营页与大屏共用。"""
    return Response.ok(financial_svc.build_dashboard(db))


@router.post(
    "/financial/upload",
    response_model=Response[UploadResult],
    summary="批量上传平台对账单(xlsx)并汇入财务指标",
    dependencies=[Depends(require_roles(*DIRECTOR_ROLES, *FINANCE_ROLES))],
)
async def upload_financial(
    file: UploadFile = File(..., description="多 Sheet 对账单 .xlsx"),
    db: Session = Depends(get_db),
):
    """解析抖音/美团/携程对账单，提取『应扣出版预付』等指标并 UPSERT（覆盖式、幂等）。"""
    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 格式的对账单文件")
    content = await file.read()
    try:
        parsed = financial_svc.parse_workbook(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"对账单解析失败：{exc}")
    if not parsed:
        raise HTTPException(status_code=400, detail="未识别到抖音/美团/携程对账单 Sheet，请检查文件")
    rows = financial_svc.upsert_metrics(db, parsed)
    detail = [financial_svc._to_platform_metric(r) for r in rows]
    return Response.ok(UploadResult(
        imported=len(rows),
        platforms=[financial_svc.PLATFORM_LABELS.get(r.platform, r.platform) for r in rows],
        total_gross_income=sum((r.gross_income for r in rows), Decimal("0")),
        detail=detail,
    ))


@router.put(
    "/financial/cost",
    response_model=Response[FinancialDashboard],
    summary="设置对账单模块投入成本",
    dependencies=[Depends(require_roles(*DIRECTOR_ROLES, *FINANCE_ROLES))],
)
def set_invested_cost(payload: InvestedCostIn, db: Session = Depends(get_db)):
    cfg = financial_svc.get_or_create_config(db)
    cfg.total_invested_cost = payload.total_invested_cost
    db.commit()
    return Response.ok(financial_svc.build_dashboard(db))


@router.put(
    "/financial/available",
    response_model=Response[FinancialDashboard],
    summary="录入可用资金",
    dependencies=[Depends(require_roles(*DIRECTOR_ROLES, *FINANCE_ROLES))],
)
def set_available_funds(payload: AvailableFundsIn, db: Session = Depends(get_db)):
    cfg = financial_svc.get_or_create_config(db)
    cfg.available_funds = payload.available_funds
    db.commit()
    return Response.ok(financial_svc.build_dashboard(db))


@router.post(
    "/projects/upload",
    response_model=Response[ProjectUploadResult],
    summary="上传供管公司项目统计表(Sheet2)并汇入项目经营指标",
    dependencies=[Depends(require_roles(*DIRECTOR_ROLES, *FINANCE_ROLES))],
)
async def upload_projects(
    file: UploadFile = File(..., description="项目投入及回款收益统计表 .xlsx(含 Sheet2)"),
    db: Session = Depends(get_db),
):
    """加载 Sheet2 项目数据（万元→元），按 (项目, 付款日期) UPSERT，覆盖式、幂等。"""
    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 格式的统计表文件")
    content = await file.read()
    try:
        parsed = project_etl.parse_sheet2(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Sheet2 解析失败：{exc}")
    if not parsed:
        raise HTTPException(status_code=400, detail="未从 Sheet2 解析到任何项目数据行")
    rows = project_etl.upsert_projects(db, parsed)
    detail = [financial_svc._to_project_metric(r) for r in rows]
    return Response.ok(ProjectUploadResult(
        imported=len(rows),
        total_invested=sum((r.invested_amount for r in rows), Decimal("0")),
        total_realized=sum((r.realized_scale for r in rows), Decimal("0")),
        total_gross_profit=sum((r.gross_profit for r in rows), Decimal("0")),
        projects=detail,
    ))
