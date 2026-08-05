"""文旅业务景区默认配置。"""
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScenicConfig(Base):
    __tablename__ = "biz_scenic_config"

    scenic_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="景区ID(作用域键)"
    )
    scenic_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="景区名称")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="展示顺序")
    default_ticket_product: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="门票台账默认产品名称"
    )
    ticket_rate_hexiao: Mapped[Decimal] = mapped_column(
        "rate_hexiao",
        Numeric(6, 4),
        nullable=False,
        default=Decimal("0.9000"),
        comment="门票默认核销率",
    )
    ticket_rate_settle: Mapped[Decimal] = mapped_column(
        "rate_settle",
        Numeric(6, 4),
        nullable=False,
        default=Decimal("0.9400"),
        comment="门票默认结算费率",
    )
    ticket_commission_rate: Mapped[Decimal] = mapped_column(
        "commission_rate",
        Numeric(6, 4),
        nullable=False,
        default=Decimal("0.0600"),
        comment="门票默认服务商佣金率",
    )
    ticket_default_commission: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True, comment="门票默认服务商佣金(NULL=按佣金率计算)"
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id"), nullable=True, comment="最后修改人"
    )
