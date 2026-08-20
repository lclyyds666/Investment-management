"""文旅业务·景区酒店平台核销台账 schema。"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ParsedPlatform(BaseModel):
    """单平台解析结果（上传即算，不落库）。"""

    platform: str = ""
    hotel_name: str = ""
    room_nights: int = 0
    order_count: int = 0
    positive_count: int = 0                        # 结算/实收为正数的订单数(核销率分子)
    base_received: Decimal = Decimal("0")          # 抖音=服务商到账;美团/携程=平台结算毛额
    suggested_commission: Decimal = Decimal("0")   # 抖音佣金建议值(可改);其他=0
    commission_rate: Decimal                         # 本次解析采用的景区配置快照
    rate_hexiao: Decimal
    rate_settle: Decimal
    # 按日期粒度逐日计算后累加的精准默认值
    def_hexiao: Decimal = Decimal("0")
    def_service_fee: Decimal = Decimal("0")
    def_jinying: Decimal = Decimal("0")
    daily_json: str = ""                            # 逐日明细(供逐日重算)
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
    commission_rate: Optional[Decimal] = None       # 缺省时由保存接口读取景区配置
    rate_hexiao: Optional[Decimal] = None
    fee_per_night: Decimal = Field(default=Decimal("44.00"))
    fee_algo: int = 1                                # 服务费算法(1=间夜×每间夜服务费;2=结算−核销)
    rate_settle: Optional[Decimal] = None           # 缺省时由保存接口读取景区配置
    jinying_amount: Optional[Decimal] = None        # 结算金额：可手工校准；算法1据此反算核销，算法2据此计算服务费
    payment_date: Optional[date] = None             # 付款日期(手工,每期共享)
    # 按日期粒度算出的精准默认值（透传，未改佣金/费率时直接采用）
    def_commission: Optional[Decimal] = None
    def_hexiao: Optional[Decimal] = None
    def_service_fee: Optional[Decimal] = None
    def_jinying: Optional[Decimal] = None
    daily_json: str = ""                            # 逐日明细(透传持久化，供编辑逐日重算)
    payment_amount: Decimal = Decimal("0")          # 付款金额(隐藏,参与递推)
    co_investment_amount: Decimal = Field(default=Decimal("0"), ge=0)  # 跟投金额(每期共享)
    repay_date: Optional[date] = None
    repay_amount: Optional[Decimal] = None
    order_count: int = 0
    positive_count: int = 0                         # 结算/实收为正数的订单数(核销率分子)
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
    base_received: Optional[Decimal] = None    # 服务商到账/平台毛额(人工覆盖;传入即清逐日明细走期级重算)
    supplier_commission: Optional[Decimal] = None
    commission_rate: Optional[Decimal] = None  # 服务商佣金率(仅抖音;改后佣金按新率逐日重算)
    rate_hexiao: Optional[Decimal] = None
    fee_per_night: Optional[Decimal] = None
    fee_algo: Optional[int] = None             # 服务费算法(1/2)
    rate_settle: Optional[Decimal] = None      # 结算费率(算法2)
    hexiao_amount: Optional[Decimal] = None    # 景区核销金额(人工覆盖；算法1结算随之更新，算法2服务费随之更新)
    jinying_amount: Optional[Decimal] = None   # 结算金额(可手工校准；算法1反算核销，算法2计算服务费)
    payment_amount: Optional[Decimal] = None
    co_investment_amount: Optional[Decimal] = Field(default=None, ge=0)
    payment_date: Optional[date] = None        # 付款日期(手工,每期共享)
    repay_date: Optional[date] = None
    repay_amount: Optional[Decimal] = None


class HotelCalculationPreview(BaseModel):
    supplier_commission: Decimal = Decimal("0")
    commission_rate: Decimal = Decimal("0.06")
    settle_base: Decimal = Decimal("0")
    hexiao_amount: Decimal = Decimal("0")
    jinying_amount: Decimal = Decimal("0")
    service_fee: Decimal = Decimal("0")


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
    commission_rate: Decimal = Decimal("0.06")
    settle_base: Decimal = Decimal("0")
    rate_hexiao: Decimal = Decimal("0.90")
    hexiao_amount: Decimal = Decimal("0")
    fee_algo: int = 1
    fee_per_night: Decimal = Decimal("44.00")
    rate_settle: Decimal = Decimal("0.94")
    service_fee: Decimal = Decimal("0")
    jinying_amount: Decimal = Decimal("0")
    payment_amount: Decimal = Decimal("0")
    co_investment_amount: Decimal = Decimal("0")
    payment_date: Optional[date] = None
    pending_writeoff: Decimal = Decimal("0")
    repay_date: Optional[date] = None
    repay_amount: Optional[Decimal] = None
    order_count: int = 0
    confirm_stored: str = ""
    confirm_name: str = ""
    confirmed: bool = False
    source_file: str = ""
    detail_stored: str = ""
    detail_name: str = ""
    created_at: Optional[datetime] = None


class HotelTotals(BaseModel):
    hexiao_amount: Decimal = Decimal("0")
    jinying_amount: Decimal = Decimal("0")
    service_fee: Decimal = Decimal("0")
    payment_amount: Decimal = Decimal("0")
    co_investment_amount: Decimal = Decimal("0")
    pending_writeoff: Decimal = Decimal("0")     # 末期各平台待核销之和
    room_nights: int = 0
    repay_amount: Decimal = Decimal("0")


class HotelLedgerOut(BaseModel):
    scenic_id: str
    rows: list[HotelLedgerRow] = []
    totals: HotelTotals = HotelTotals()
    total: int = 0
