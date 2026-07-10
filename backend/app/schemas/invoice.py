"""发票管理 schema。"""
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.core.enums import INVOICE_STATUS_LABELS, InvoiceStatus


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


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    invoice_title: Optional[str] = None
    tax_no: Optional[str] = None
    invoice_type: Optional[str] = None
    amount: Optional[Decimal] = None
    status: Optional[InvoiceStatus] = None
    customer_name: Optional[str] = None
    contract_no: Optional[str] = None
    issued_date: Optional[date] = None
    remark: Optional[str] = None


class InvoiceOut(InvoiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int

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
