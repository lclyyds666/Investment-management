"""Daily per-user receipts for fund maturity alerts."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FundAlertReceipt(Base):
    __tablename__ = "biz_fund_alert_receipt"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "fund_id",
            "alert_date",
            "stage",
            name="uq_fund_alert_receipt_daily_stage",
        ),
        Index("ix_fund_alert_receipt_lookup", "user_id", "alert_date", "stage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fund_id: Mapped[int] = mapped_column(
        ForeignKey("biz_fund_transaction.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_date: Mapped[date] = mapped_column(Date, nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    shown_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
