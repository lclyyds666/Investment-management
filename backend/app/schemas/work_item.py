from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


class WorkItemOut(BaseModel):
    id: str
    item_type: str
    scenic_id: str | None = None
    contract_id: int | None = None
    contract_name: str | None = None
    amount: Decimal
    due_date: date | None = None
    status: str
    priority: int = 2
    target_path: str
    target_query: dict[str, str] = Field(default_factory=dict)


class ContractClosureSummary(BaseModel):
    approved_payment: Decimal | None = None
    pending_payment: Decimal | None = None
    actual_payment: Decimal | None = None
    output_invoiced: Decimal | None = None
    actual_receipt: Decimal | None = None
    missing_input_invoice: Decimal | None = None
