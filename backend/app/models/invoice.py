"""发票管理模型（财务模块扩展）。"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    InvoiceApprovalStatus,
    InvoiceDirection,
    InvoiceSourceKind,
    InvoiceStatus,
)
from app.db.base import Base


class Invoice(Base):
    __tablename__ = "biz_invoice"
    __table_args__ = (
        UniqueConstraint(
            "direction", "source_kind", "scenic_id", "period_key",
            name="uq_invoice_source",
        ),
    )

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

    direction: Mapped[InvoiceDirection | None] = mapped_column(
        SAEnum(InvoiceDirection, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        nullable=True, index=True, comment="发票方向(input=进项/output=销项)",
    )
    source_kind: Mapped[InvoiceSourceKind | None] = mapped_column(
        SAEnum(InvoiceSourceKind, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        nullable=True, index=True, comment="台账来源(ticket/hotel)",
    )
    scenic_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="景区作用域键")
    period_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True, comment="来源台账周期")
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="来源确认版本")
    source_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="来源明细指纹")
    generated_by_source: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False, comment="是否由台账确认生成")
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_customer.id", ondelete="SET NULL"), nullable=True, index=True, comment="客户档案",
    )
    customer_social_credit_code: Mapped[str] = mapped_column(String(32), default="", comment="客户统一社会信用代码快照")
    customer_address: Mapped[str] = mapped_column(String(255), default="", comment="客户地址快照")
    customer_phone: Mapped[str] = mapped_column(String(32), default="", comment="客户电话快照")
    customer_bank_name: Mapped[str] = mapped_column(String(128), default="", comment="客户开户行快照")
    customer_bank_account: Mapped[str] = mapped_column(String(64), default="", comment="客户银行账号快照")
    workflow_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("wf_instance.id", ondelete="SET NULL"), nullable=True, index=True, comment="审批工作流实例",
    )
    approval_status: Mapped[InvoiceApprovalStatus | None] = mapped_column(
        SAEnum(InvoiceApprovalStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        nullable=True, default=InvoiceApprovalStatus.DRAFT, comment="销项审批状态",
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="来源生成时间")
    source_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="来源同步时间")

    attachments: Mapped[list["InvoiceAttachment"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", passive_deletes=True,
    )
    details: Mapped[list["InvoiceDetail"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", passive_deletes=True,
    )


class InvoiceAttachment(Base):
    __tablename__ = "biz_invoice_attachment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("biz_invoice.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="attachments")


class InvoiceDetail(Base):
    __tablename__ = "biz_invoice_detail"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("biz_invoice.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_kind: Mapped[InvoiceSourceKind | None] = mapped_column(
        SAEnum(InvoiceSourceKind, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    item_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)

    invoice: Mapped[Invoice] = relationship(back_populates="details")
