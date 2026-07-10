"""经营数据模型（用于可视化看板）。

按 "年月 + 业务条线" 记录经营指标，
便于按月趋势、按条线占比等多维度聚合。
"""
from decimal import Decimal

from sqlalchemy import Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperationData(Base):
    __tablename__ = "biz_operation_data"
    __table_args__ = (
        UniqueConstraint("year", "month", "business_line", name="uq_period_line"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    year: Mapped[int] = mapped_column(Integer, index=True, nullable=False, comment="年份")
    month: Mapped[int] = mapped_column(Integer, nullable=False, comment="月份 1-12")
    business_line: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="业务条线，如 图书发行/数字出版/物流仓储"
    )
    revenue: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="营收(元)")
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="成本(元)")
    profit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="利润(元)")
    order_count: Mapped[int] = mapped_column(Integer, default=0, comment="订单数")
