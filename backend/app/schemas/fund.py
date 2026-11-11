"""Schemas and validation rules for fund management transactions."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


INCREASE_CATEGORIES = frozenset({
    "bank_credit",
    "company_loan",
    "customer_payment",
    "own_funds",
    "other",
})
USAGE_CATEGORIES = frozenset({
    "business_payment",
    "expense",
    "principal_interest_payment",
    "other",
})
DUE_CATEGORIES = frozenset({"bank_credit", "company_loan"})
class FundTransactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: str
    category: str
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    occurred_on: date
    counterparty: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=300)
    maturity_date: date | None = None
    remark: str = ""
    bank_reference: str = Field(default="", max_length=128)

    @model_validator(mode="after")
    def validate_transaction(self):
        categories = (
            INCREASE_CATEGORIES if self.direction == "increase"
            else USAGE_CATEGORIES if self.direction == "usage"
            else None
        )
        if categories is None:
            raise ValueError("direction must be 'increase' or 'usage'.")
        if self.category not in categories:
            raise ValueError("category is not valid for the selected direction.")
        if self.category in DUE_CATEGORIES and self.maturity_date is None:
            raise ValueError("bank credit and company loans require a maturity date.")
        return self


class FundTransactionCreate(FundTransactionInput):
    pass


class FundTransactionUpdate(FundTransactionInput):
    pass


class FundSettleIn(BaseModel):
    settled_on: date | None = None


class FundLegacyAssociationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_id: int = Field(gt=0)
    approval_form_id: int | None = Field(default=None, gt=0)


class FundTransactionOut(FundTransactionInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    settlement_status: str = "open"
    settled_on: date | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    maturity_status: str = "normal"
    execution_task_id: int | None = None
    contract_id: int | None = None
    approval_form_id: int | None = None
    invoice_id: int | None = None
    scenic_id: str | None = None


class FundSummary(BaseModel):
    available_funds: Decimal = Decimal("0")
    total_increase: Decimal = Decimal("0")
    total_usage: Decimal = Decimal("0")
    due_within_30_amount: Decimal = Decimal("0")
    due_within_30_count: int = 0
    overdue_count: int = 0


class FundAlertItem(BaseModel):
    id: int
    category: str
    counterparty: str = ""
    summary: str = ""
    amount: Decimal
    maturity_date: date
    days_remaining: int
    stage: Literal["due_soon", "overdue"]


class FundAlertToday(BaseModel):
    alert_date: date
    items: list[FundAlertItem] = Field(default_factory=list)


class FundAlertReceiptItem(BaseModel):
    fund_id: int = Field(gt=0)
    stage: Literal["due_soon", "overdue"]


class FundAlertAcknowledgeIn(BaseModel):
    items: list[FundAlertReceiptItem] = Field(default_factory=list, max_length=200)
