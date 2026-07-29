"""财务经营指标 schema。"""
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


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

    # 所有字段均直接由门票/酒店台账聚合。
    existing_scale: Decimal = Decimal("0")         # 已投入业务规模 = Σ(付款金额-跟投金额)
    total_realized_scale: Decimal = Decimal("0")   # 已实现业务规模 = Σ销售额(jinying_amount)
    total_gross_income: Decimal = Decimal("0")     # 已实现业务毛利润 = Σ服务费
    capital_occupation_days: Optional[float] = None # 净投入金额加权平均资金占用天数
    ledger_profit: List[LedgerProfitPoint] = []
    available_years: List[int] = []
    scenic_ids: List[str] = []
