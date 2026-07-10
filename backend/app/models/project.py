"""供管公司项目投入与回款收益模型（源自年度项目统计表 Sheet2）。

按「项目」维度记录投入金额、回款、毛利、收益率等；金额统一以元存储
（原表单位为万元，入库时 ×10000）。平台列仅作标签展示，不做拆分。
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectMetrics(Base):
    __tablename__ = "biz_project_metrics"
    __table_args__ = (
        UniqueConstraint("project_name", "pay_date", name="uq_project_paydate"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    seq: Mapped[int] = mapped_column(Integer, default=0, comment="序号")
    project_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="项目名称")
    platforms: Mapped[str] = mapped_column(String(200), default="", comment="平台(标签，如 抖音、携程、美团)")
    invested_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="投入金额(元) = 现存业务规模/已投入本金"
    )
    realized_scale: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="回款小计(元) = 已实现业务规模"
    )
    gross_profit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="实现毛利(元) = 已实现业务毛收入"
    )
    profit_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 4), nullable=True, comment="收益率(小数，如 0.0473)"
    )
    pay_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="付款日期")
    term_months: Mapped[str] = mapped_column(String(16), default="", comment="合同期限(月)")
