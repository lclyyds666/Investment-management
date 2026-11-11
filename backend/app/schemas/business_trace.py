"""Explicit read-only trace projections; never serialize source ORM records."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.enums import InvoiceSourceKind


class TracePeriodOut(BaseModel):
    scenic_id: str
    source_kind: InvoiceSourceKind
    period_key: str
    period_end: date | None = None


class TraceLedgerOut(BaseModel):
    id: int
    scenic_id: str
    platform: str
    confirmed: bool


class TraceInvoiceOut(BaseModel):
    id: int
    direction: str | None
    status: str
    amount: Decimal


class TraceAllocationOut(BaseModel):
    id: int
    invoice_id: int
    fund_transaction_id: int
    amount: Decimal


class TraceFundOut(BaseModel):
    id: int
    direction: str
    amount: Decimal
    occurred_on: date


class TraceExecutionTaskOut(BaseModel):
    id: int
    direction: str
    status: str
    planned_amount: Decimal
    executed_amount: Decimal


class TraceApprovalOut(BaseModel):
    id: int
    form_type: str
    status: str


class TraceContractOut(BaseModel):
    id: int
    contract_no: str
    status: str


class BusinessTraceOut(TracePeriodOut):
    ledger_rows: list[TraceLedgerOut] = Field(default_factory=list)
    invoices: list[TraceInvoiceOut] = Field(default_factory=list)
    allocations: list[TraceAllocationOut] = Field(default_factory=list)
    funds: list[TraceFundOut] = Field(default_factory=list)
    execution_tasks: list[TraceExecutionTaskOut] = Field(default_factory=list)
    approvals: list[TraceApprovalOut] = Field(default_factory=list)
    contracts: list[TraceContractOut] = Field(default_factory=list)
    restricted_count: int = 0
