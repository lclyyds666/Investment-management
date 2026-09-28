"""发票管理 schema。"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from app.core.enums import (
    INVOICE_STATUS_LABELS,
    InvoiceApprovalStatus,
    InvoiceDirection,
    InvoiceSourceKind,
    InvoiceStatus,
)


class InvoiceBase(BaseModel):
    invoice_title: str
    tax_no: str = ""
    invoice_type: str = "增值税专用发票"
    amount: Decimal = Decimal("0")
    status: InvoiceStatus = InvoiceStatus.PENDING
    customer_name: str = ""
    contract_no: str = ""
    issued_date: Optional[date] = None
    remark: str = ""
    direction: Optional[InvoiceDirection] = None
    source_kind: Optional[InvoiceSourceKind] = None
    scenic_id: Optional[str] = None
    period_key: Optional[str] = None
    source_revision: Optional[int] = None
    source_fingerprint: Optional[str] = None
    generated_by_source: Optional[bool] = None
    customer_id: Optional[int] = None
    customer_social_credit_code: str = ""
    customer_address: str = ""
    customer_phone: str = ""
    customer_bank_name: str = ""
    customer_bank_account: str = ""


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_title: str
    tax_no: str = ""
    invoice_type: str = "增值税专用发票"
    amount: Decimal = Decimal("0")
    customer_name: str = ""
    contract_no: str = ""
    issued_date: Optional[date] = None
    remark: str = ""
    customer_social_credit_code: str = ""
    customer_address: str = ""
    customer_phone: str = ""
    customer_bank_name: str = ""
    customer_bank_account: str = ""


class InvoiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_title: Optional[str] = None
    tax_no: Optional[str] = None
    amount: Optional[Decimal] = None
    customer_name: Optional[str] = None
    contract_no: Optional[str] = None
    remark: Optional[str] = None
    customer_social_credit_code: Optional[str] = None
    customer_address: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_bank_name: Optional[str] = None
    customer_bank_account: Optional[str] = None

    @field_validator(
        "invoice_title",
        "tax_no",
        "amount",
        "customer_name",
        "contract_no",
        "remark",
        "customer_social_credit_code",
        "customer_address",
        "customer_phone",
        "customer_bank_name",
        "customer_bank_account",
        mode="before",
    )
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("字段不可为 null")
        return value


class InvoiceDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    line_no: int
    source_row_id: Optional[int] = None
    source_kind: Optional[InvoiceSourceKind] = None
    platform: str = ""
    item_name: str = ""
    amount: Decimal = Decimal("0")


class InvoiceDetailUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Optional[Decimal] = None
    platform: Optional[str] = None
    item_name: Optional[str] = None

    @field_validator("amount", "platform", "item_name", mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("字段不可为 null")
        return value


class InvoiceDetailList(BaseModel):
    items: list[InvoiceDetailOut]
    detail_total: Decimal
    difference: Decimal


class InvoiceAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    original_name: str
    content_type: str
    file_size: int
    uploaded_by: Optional[int] = None
    uploaded_at: Optional[datetime] = None


class InvoiceOut(InvoiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_instance_id: Optional[int] = None
    approval_status: Optional[InvoiceApprovalStatus] = None
    generated_at: Optional[datetime] = None
    source_synced_at: Optional[datetime] = None

    @computed_field
    @property
    def status_label(self) -> str:
        return INVOICE_STATUS_LABELS.get(self.status.value, self.status.value)


class InvoiceStats(BaseModel):
    total: int
    pending: int
    issued: int
    void: int
    issued_amount: Decimal
    pending_amount: Decimal


class InvoiceRecordStats(BaseModel):
    attachment_count: int
    detail_count: int
    detail_total: Decimal
    difference: Decimal
