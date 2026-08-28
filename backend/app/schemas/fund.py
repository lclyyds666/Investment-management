"""Schemas and validation rules for fund management transactions."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

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
SETTLEMENT_STATUSES = frozenset({"open", "settled"})


class FundTransactionWrite(BaseModel):
    direction: str
    category: str
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    occurred_on: date
    counterparty: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=300)
    maturity_date: date | None = None
    settlement_status: str = "open"
    settled_on: date | None = None
    remark: str = ""

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
        if self.settlement_status not in SETTLEMENT_STATUSES:
            raise ValueError("settlement_status must be 'open' or 'settled'.")
        if self.settlement_status == "settled" and self.category not in DUE_CATEGORIES:
            raise ValueError("only bank credit and company loans can be settled.")
        if self.settled_on is not None and self.settled_on < self.occurred_on:
            raise ValueError("settled_on cannot be earlier than occurred_on.")
        return self


class FundTransactionCreate(FundTransactionWrite):
    pass


class FundTransactionUpdate(FundTransactionWrite):
    pass


class FundTransactionOut(FundTransactionWrite):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    maturity_status: str = "normal"


class FundSummary(BaseModel):
    available_funds: Decimal = Decimal("0")
    total_increase: Decimal = Decimal("0")
    total_usage: Decimal = Decimal("0")
    due_within_30_amount: Decimal = Decimal("0")
    due_within_30_count: int = 0
    overdue_count: int = 0
