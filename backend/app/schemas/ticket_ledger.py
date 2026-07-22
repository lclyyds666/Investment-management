"""文旅业务·门票平台核销业务台账 schema。"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ParsedFile(BaseModel):
    """单个对账明细文件解析结果（上传即算，不落库；供前端录入服务商佣金/付款金额等）。"""

    source_file: str = ""
    # 明细源文件已落盘，供预览/下载；保存台账时随行持久化
    detail_stored: str = ""
    detail_name: str = ""
    supplier_received: Decimal = Decimal("0")   # 服务商到账金额（明细算）
    order_count: int = 0
    period_text: str = ""                        # 对账周期文本
    check_date_text: str = ""                    # 核对日期（=周期）
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    sheets: list[str] = []


class ParseResult(BaseModel):
    """批量解析结果。"""

    scenic_id: str
    files: list[ParsedFile] = []
    succeeded: int = 0
    failed: int = 0
    warnings: list[str] = []


class TicketLedgerSaveRow(BaseModel):
    """前端确认后提交的一行（服务商佣金/付款金额与手工字段；出版应得由后端算）。"""

    pay_date: Optional[date] = None
    platform: str = ""
    ticket_product: str = "水上世界/童话世界/海洋王国"
    check_date_text: str = ""
    period_text: str = ""
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    supplier_received: Decimal = Decimal("0")
    supplier_commission: Decimal = Decimal("0")     # 服务商佣金（手工，默认0）
    payment_amount: Decimal = Decimal("0")          # 付款金额（手工，期次递推输入）
    rate_hexiao: Decimal = Field(default=Decimal("0.90"))
    rate_fee: Decimal = Field(default=Decimal("0.04"))
    order_count: int = 0
    repay_date: Optional[date] = None
    repay_amount: Optional[Decimal] = None
    source_file: str = ""
    detail_stored: str = ""
    detail_name: str = ""


class TicketLedgerSaveIn(BaseModel):
    """保存台账请求：一批行落库。单期上传恒为追加(append)，滚动余额由后端集中重算。"""

    rows: list[TicketLedgerSaveRow] = []
    mode: str = Field(default="append", description="append=追加(默认)；replace=覆盖该景区台账")


class TicketLedgerUpdateIn(BaseModel):
    """编辑单行（回款、付款日期、平台、服务商佣金、付款金额、比例等；提供的字段才更新）。"""

    pay_date: Optional[date] = None
    platform: Optional[str] = None
    ticket_product: Optional[str] = None
    supplier_commission: Optional[Decimal] = None
    payment_amount: Optional[Decimal] = None
    rate_hexiao: Optional[Decimal] = None
    rate_fee: Optional[Decimal] = None
    repay_date: Optional[date] = None
    repay_amount: Optional[Decimal] = None


class TicketLedgerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenic_id: str
    row_no: int = 0
    pay_date: Optional[date] = None
    platform: str = ""
    ticket_product: str = ""
    check_date_text: str = ""
    period_text: str = ""
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    supplier_received: Decimal = Decimal("0")
    supplier_commission: Decimal = Decimal("0")
    publisher_due: Decimal = Decimal("0")
    hexiao_amount: Decimal = Decimal("0")
    payment_amount: Decimal = Decimal("0")
    pending_writeoff: Decimal = Decimal("0")
    jinying_amount: Decimal = Decimal("0")
    service_fee: Decimal = Decimal("0")
    rate_hexiao: Decimal = Decimal("0.90")
    rate_fee: Decimal = Decimal("0.04")
    order_count: int = 0
    repay_date: Optional[date] = None
    repay_amount: Optional[Decimal] = None
    source_file: str = ""
    detail_stored: str = ""
    detail_name: str = ""
    created_at: Optional[datetime] = None


class TicketLedgerTotals(BaseModel):
    """合计行。"""

    hexiao_amount: Decimal = Decimal("0")
    payment_amount: Decimal = Decimal("0")
    pending_writeoff: Decimal = Decimal("0")   # 末期滚动余额
    jinying_amount: Decimal = Decimal("0")
    service_fee: Decimal = Decimal("0")
    publisher_due: Decimal = Decimal("0")
    repay_amount: Decimal = Decimal("0")


class TicketLedgerOut(BaseModel):
    """台账查询结果：行 + 合计。"""

    scenic_id: str
    rows: list[TicketLedgerRow] = []
    totals: TicketLedgerTotals = TicketLedgerTotals()
    total: int = 0
