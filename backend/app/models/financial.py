"""财务经营指标模型（源自平台对账单的真实回款数据）。

- FinancialMetrics：按「平台 + 账期」记录已实现业务规模/毛收入（回款）等指标，
  由对账单 xlsx 上传解析后 UPSERT 写入，重复上传同账期覆盖不累加。
- FinanceConfig：单行配置，存放领导手工录入的「投入成本」，
  用于实时计算业务收益率、资金占用、可用资金。
"""
from decimal import Decimal

from sqlalchemy import Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinancialMetrics(Base):
    __tablename__ = "biz_financial_metrics"
    __table_args__ = (
        UniqueConstraint("platform", "period", name="uq_platform_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment="平台 douyin/meituan/ctrip")
    period: Mapped[str] = mapped_column(String(32), nullable=False, comment="账期，如 2026-06-24~06-30")
    realized_scale: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="已实现业务规模(出版应得到账金额)"
    )
    gross_income: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="已实现业务毛收入(应扣出版预付/回款)"
    )
    gmv: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True, comment="订单实收金额GMV(可选，抖音对账单提供)"
    )
    order_count: Mapped[int] = mapped_column(Integer, default=0, comment="订单数(明细统计)")
    room_nights: Mapped[int] = mapped_column(Integer, default=0, comment="间夜(明细统计)")


class FinanceConfig(Base):
    __tablename__ = "biz_finance_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    total_invested_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="投入成本(领导手工录入，用于对账单模块收益率)"
    )
    available_funds: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="可用资金(手工录入，暂空后续填)"
    )
