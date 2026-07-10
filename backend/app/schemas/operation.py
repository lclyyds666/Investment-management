"""经营数据相关 schema。"""
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict


class OperationDataBase(BaseModel):
    year: int
    month: int
    business_line: str
    revenue: Decimal = Decimal("0")
    cost: Decimal = Decimal("0")
    profit: Decimal = Decimal("0")
    order_count: int = 0


class OperationDataCreate(OperationDataBase):
    pass


class OperationDataOut(OperationDataBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------- 可视化看板聚合返回结构 ----------

class KpiSummary(BaseModel):
    total_revenue: Decimal
    total_cost: Decimal
    total_profit: Decimal
    total_orders: int


class TrendPoint(BaseModel):
    month: str  # 形如 "2026-01"
    revenue: Decimal
    profit: Decimal


class LineShare(BaseModel):
    business_line: str
    revenue: Decimal


class DashboardData(BaseModel):
    kpi: KpiSummary
    trend: List[TrendPoint]
    line_share: List[LineShare]
