"""发票管理模型（财务模块扩展）。"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum as SAEnum, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import InvoiceStatus
from app.db.base import Base


class Invoice(Base):
    __tablename__ = "biz_invoice"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    invoice_title: Mapped[str] = mapped_column(String(200), nullable=False, comment="发票抬头")
    tax_no: Mapped[str] = mapped_column(String(64), default="", comment="纳税人识别号(税号)")
    invoice_type: Mapped[str] = mapped_column(String(32), default="增值税专用发票", comment="发票类型")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="开票金额(元)")
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        default=InvoiceStatus.PENDING,
        nullable=False,
        comment="开票状态",
    )
    customer_name: Mapped[str] = mapped_column(String(200), default="", comment="客户名称")
    contract_no: Mapped[str] = mapped_column(String(64), default="", comment="关联合同编号")
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="开票日期")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")
