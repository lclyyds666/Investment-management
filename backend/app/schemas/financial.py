"""财务经营指标 schema。"""
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class PlatformMetric(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform: str
    platform_label: str = ""
    period: str = ""
    realized_scale: Decimal = Decimal("0")   # 已实现业务规模
    gross_income: Decimal = Decimal("0")     # 已实现业务毛收入(回款)
    gmv: Optional[Decimal] = None
    order_count: int = 0
    room_nights: int = 0


class ProjectMetric(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int = 0
    project_name: str
    platforms: str = ""
    invested_amount: Decimal = Decimal("0")   # 投入金额(现存业务规模/已投入本金)
    realized_scale: Decimal = Decimal("0")    # 回款小计(已实现业务规模)
    gross_profit: Decimal = Decimal("0")      # 实现毛利(已实现业务毛收入)
    profit_rate: Optional[Decimal] = None     # 收益率(小数)
    pay_date: Optional[str] = None
    term_months: str = ""
    capital_occupied: Decimal = Decimal("0")  # 资金占用 = 投入 - 回款(由端点补充)


class FinancialDashboard(BaseModel):
    """经营页 / 大屏共用的财务聚合视图（项目维度驱动）。"""

    # —— 项目维度聚合（Sheet2 驱动）——
    existing_scale: Decimal = Decimal("0")         # 现存业务规模 = Σ投入(已投入本金)
    total_realized_scale: Decimal = Decimal("0")   # 已实现业务规模 = Σ回款小计
    total_gross_income: Decimal = Decimal("0")     # 已实现业务毛收入 = Σ实现毛利
    profit_rate: Optional[float] = None            # 业务收益率 %(投入加权平均)
    capital_occupied: Decimal = Decimal("0")       # 资金占用 = Σ投入 - Σ回款
    available_funds: Decimal = Decimal("0")        # 可用资金(手工录入)
    projects: List[ProjectMetric] = []             # 项目明细
    # —— 对账单平台明细（独立数据源，保留）——
    invested_cost: Decimal = Decimal("0")          # 对账单模块投入成本(手工录入)
    platforms: List[PlatformMetric] = []


class InvestedCostIn(BaseModel):
    total_invested_cost: Decimal


class AvailableFundsIn(BaseModel):
    available_funds: Decimal


class ProjectUploadResult(BaseModel):
    imported: int = 0
    total_invested: Decimal = Decimal("0")
    total_realized: Decimal = Decimal("0")
    total_gross_profit: Decimal = Decimal("0")
    projects: List[ProjectMetric] = []


class UploadResult(BaseModel):
    imported: int = 0
    platforms: List[str] = []
    total_gross_income: Decimal = Decimal("0")
    detail: List[PlatformMetric] = []
