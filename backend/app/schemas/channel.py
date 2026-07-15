"""多渠道数据集成 schema。"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.core.enums import CHANNEL_CATEGORY_LABELS


class ChannelBase(BaseModel):
    name: str
    biz_type: str = "文旅业务"
    category: str = "other"
    url: str = ""
    account: str = ""
    password: str = ""
    logo: str = "🔗"
    description: str = ""
    sort_order: int = 0


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    biz_type: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    account: Optional[str] = None
    password: Optional[str] = None
    logo: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class ChannelOut(ChannelBase):
    model_config = ConfigDict(from_attributes=True)

    id: int

    @computed_field
    @property
    def category_label(self) -> str:
        return CHANNEL_CATEGORY_LABELS.get(self.category, self.category)


class ChannelMapping(BaseModel):
    """渠道表格列 → 经营指标字段映射。business_line 为空时后端用渠道名兜底。"""

    date_col: str = ""       # 日期列（支持 2026-06 / 2026-06-01 / 2026年6月 等）
    revenue_col: str = ""    # 营收/交易金额列
    cost_col: str = ""       # 成本列（可选）
    order_col: str = ""      # 订单数列（可选）
    business_line: str = ""  # 汇入经营表时使用的业务条线（建议每渠道唯一）


class ChannelDataIn(BaseModel):
    columns: list[str] = []
    rows: list[list] = []
    mapping: Optional[ChannelMapping] = None


class SyncResult(BaseModel):
    """渠道数据汇入经营表的结果摘要。"""

    synced: bool = False
    reason: str = ""
    business_line: str = ""
    months: int = 0
    rows_used: int = 0
    rows_skipped: int = 0
    total_revenue: float = 0.0


class ChannelDataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_id: int
    columns: Optional[list] = None
    rows: Optional[list] = None
    mapping: Optional[ChannelMapping] = None
    sync: Optional[SyncResult] = None
