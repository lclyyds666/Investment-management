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
    invested_amount: Decimal = Decimal("0")   # 独立项目统计表投入金额
    realized_scale: Decimal = Decimal("0")    # 独立项目统计表回款小计
    gross_profit: Decimal = Decimal("0")      # 独立项目统计表实现毛利
    profit_rate: Optional[Decimal] = None     # 收益率(小数)
    pay_date: Optional[str] = None
    term_months: str = ""
    capital_occupied: Decimal = Decimal("0")  # 资金占用 = 投入 - 回款(由端点补充)


class LedgerProfitPoint(BaseModel):
    """经营图表的最小统计单元：景区 + 门票/酒店 + 期次。"""

    scenic_id: str
    business_type: str
    period: str
    period_key: str
    year: Optional[int] = None
    month: Optional[int] = None
    service_fee: Decimal = Decimal("0")


class FinancialDashboard(BaseModel):
    """经营页 / 大屏共用的财务聚合视图。"""

    # 三项经营核心指标直接由门票/酒店台账聚合。
    existing_scale: Decimal = Decimal("0")         # 已投入业务规模 = Σ(付款金额-跟投金额)
    total_realized_scale: Decimal = Decimal("0")   # 已实现业务规模 = Σ销售额(jinying_amount)
    total_gross_income: Decimal = Decimal("0")     # 已实现业务毛利润 = Σ服务费
    profit_rate: Optional[float] = None             # 业务收益率 = 毛利润/净投入
    capital_occupation_days: Optional[float] = None # 净投入金额加权平均资金占用天数
    capital_occupied: Decimal = Decimal("0")        # 兼容旧调用方：净投入-已回款
    available_funds: Decimal = Decimal("0")        # 可用资金(手工录入)
    ledger_profit: List[LedgerProfitPoint] = []
    available_years: List[int] = []
    scenic_ids: List[str] = []
    # 项目统计表仍作为独立历史数据源返回，避免影响现有大屏/上传功能。
    projects: List[ProjectMetric] = []
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
