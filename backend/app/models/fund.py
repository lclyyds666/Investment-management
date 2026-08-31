"""Fund management transaction ledger model."""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FundTransaction(Base):
    __tablename__ = "biz_fund_transaction"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    counterparty: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(String(300), default="")
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    settlement_status: Mapped[str] = mapped_column(String(16), default="open")
    settled_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"), nullable=True)
