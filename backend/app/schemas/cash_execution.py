from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CashExecutionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    occurred_on: date
    counterparty: str = Field(default="", max_length=200)
    bank_reference: str = Field(default="", max_length=128)
    summary: str = Field(default="", max_length=300)
    remark: str = ""


class CashExecutionTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: str
    approval_form_id: int | None = None
    invoice_id: int | None = None
    contract_id: int | None = None
    scenic_id: str
    planned_amount: Decimal
    executed_amount: Decimal
    status: str
