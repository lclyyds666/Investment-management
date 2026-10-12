"""Cash execution tasks and invoice-to-fund reconciliation records."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CashTaskStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CashExecutionTask(Base):
    __tablename__ = "biz_cash_execution_task"
    __table_args__ = (
        UniqueConstraint("approval_form_id", name="uq_cash_task_approval"),
        UniqueConstraint("invoice_id", name="uq_cash_task_invoice"),
        CheckConstraint(
            "(direction = 'outflow' AND approval_form_id IS NOT NULL AND invoice_id IS NULL) OR "
            "(direction = 'inflow' AND invoice_id IS NOT NULL AND approval_form_id IS NULL)",
            name="ck_cash_task_single_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    approval_form_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_approval_form.id", ondelete="RESTRICT"), nullable=True
    )
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_invoice.id", ondelete="RESTRICT"), nullable=True
    )
    contract_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_contract.id", ondelete="SET NULL"), nullable=True
    )
    scenic_id: Mapped[str] = mapped_column(String(64), nullable=False)
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    executed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CashTaskStatus.PENDING.value
    )


class InvoiceFundAllocation(Base):
    __tablename__ = "biz_invoice_fund_allocation"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fund_transaction_id: Mapped[int] = mapped_column(
        ForeignKey("biz_fund_transaction.id", ondelete="CASCADE"), nullable=False
    )
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("biz_invoice.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    allocated_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), nullable=False)

    fund_transaction = relationship("FundTransaction", back_populates="allocations")
    invoice = relationship("Invoice", back_populates="fund_allocations")


from app.models.fund import FundTransaction  # noqa: E402,F401
from app.models.invoice import Invoice  # noqa: E402,F401
