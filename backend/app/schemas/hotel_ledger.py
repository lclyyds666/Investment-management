"""文旅业务·景区酒店平台核销台账 schema。"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ParsedPlatform(BaseModel):
    """单平台解析结果（上传即算，不落库）。"""

    platform: str = ""
    room_nights: int = 0
    order_count: int = 0
    base_received: Decimal = Decimal("0")          # 抖音=服务商到账;美团/携程=平台结算毛额
    suggested_commission: Decimal = Decimal("0")   # 抖音佣金建议值(可改);其他=0
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    period_text: str = ""
    check_date_text: str = ""


class ParseResult(BaseModel):
    scenic_id: str
    source_file: str = ""
    detail_stored: str = ""
    detail_name: str = ""
    platforms: list[ParsedPlatform] = []
    warnings: list[str] = []


class HotelSaveRow(BaseModel):
    platform: str = ""
    hotel_name: str = ""
    check_date_text: str = ""
    period_text: str = ""
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    room_nights: int = 0
    base_received: Decimal = Decimal("0")
    supplier_commission: Decimal = Decimal("0")
    rate_hexiao: Decimal = Field(default=Decimal("0.90"))
    fee_per_night: Decimal = Field(default=Decimal("44.00"))
    jinying_amount: Optional[Decimal] = None        # 结算金额：默认公式算,可编辑覆盖
    payment_amount: Decimal = Decimal("0")          # 付款金额(隐藏,参与递推)
    repay_date: Optional[date] = None
    repay_amount: Optional[Decimal] = None
    order_count: int = 0
    source_file: str = ""
    detail_stored: str = ""
    detail_name: str = ""


class HotelSaveIn(BaseModel):
    rows: list[HotelSaveRow] = []
    mode: str = Field(default="append", description="append=追加(默认)；replace=覆盖该景区台账")


class HotelUpdateIn(BaseModel):
    """编辑单行（佣金[抖音]/核销率/每间夜服务费/间夜/付款金额/回款）。"""

    platform: Optional[str] = None
    hotel_name: Optional[str] = None
    room_nights: Optional[int] = None
    supplier_commission: Optional[Decimal] = None
    rate_hexiao: Optional[Decimal] = None
    fee_per_night: Optional[Decimal] = None
    jinying_amount: Optional[Decimal] = None   # 结算金额(可编辑覆盖值)
    payment_amount: Optional[Decimal] = None
    repay_date: Optional[date] = None
    repay_amount: Optional[Decimal] = None


class HotelLedgerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenic_id: str
    row_no: int = 0
    platform: str = ""
    hotel_name: str = ""
    check_date_text: str = ""
    period_text: str = ""
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    room_nights: int = 0
    base_received: Decimal = Decimal("0")
    supplier_commission: Decimal = Decimal("0")
    settle_base: Decimal = Decimal("0")
    rate_hexiao: Decimal = Decimal("0.90")
    hexiao_amount: Decimal = Decimal("0")
    fee_per_night: Decimal = Decimal("44.00")
    service_fee: Decimal = Decimal("0")
    jinying_amount: Decimal = Decimal("0")
    payment_amount: Decimal = Decimal("0")
    pending_writeoff: Decimal = Decimal("0")
    repay_date: Optional[date] = None
    repay_amount: Optional[Decimal] = None
    order_count: int = 0
    source_file: str = ""
    detail_stored: str = ""
    detail_name: str = ""
    created_at: Optional[datetime] = None


class HotelTotals(BaseModel):
    hexiao_amount: Decimal = Decimal("0")
    jinying_amount: Decimal = Decimal("0")
    service_fee: Decimal = Decimal("0")
    payment_amount: Decimal = Decimal("0")
    pending_writeoff: Decimal = Decimal("0")     # 末期各平台待核销之和
    room_nights: int = 0
    repay_amount: Decimal = Decimal("0")


class HotelLedgerOut(BaseModel):
    scenic_id: str
    rows: list[HotelLedgerRow] = []
    totals: HotelTotals = HotelTotals()
    total: int = 0
