"""景区核销台账默认配置模型。"""
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Numeric, SmallInteger, String, text
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScenicConfig(Base):
    __tablename__ = "biz_scenic_config"
    __table_args__ = (
        CheckConstraint("rate_hexiao >= 0 AND rate_hexiao <= 1", name="chk_scenic_cfg_rate_hexiao"),
        CheckConstraint("rate_settle >= 0 AND rate_settle <= 1", name="chk_scenic_cfg_rate_settle"),
        CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 1",
            name="chk_scenic_cfg_commission_rate",
        ),
        CheckConstraint("hotel_fee_algo IN (1, 2)", name="chk_scenic_cfg_hotel_fee_algo"),
        CheckConstraint("fee_per_night >= 0", name="chk_scenic_cfg_fee_per_night"),
        Index("idx_scenic_config_enabled_sort", "enabled", "sort_order"),
    )

    scenic_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, nullable=False, comment="景区ID(作用域键)"
    )
    scenic_name: Mapped[str] = mapped_column(
        String(128), default="", server_default="", nullable=False, comment="景区名称"
    )
    image_url: Mapped[str] = mapped_column(
        String(500), default="", server_default="", nullable=False, comment="景区展示图片地址"
    )
    ticket_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1"), nullable=False, comment="是否启用门票台账模块"
    )
    hotel_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1"), nullable=False, comment="是否启用酒店台账模块"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False, comment="景区展示顺序"
    )
    default_ticket_product: Mapped[str] = mapped_column(
        String(200), default="", server_default="", nullable=False, comment="门票产品名默认值"
    )
    default_hotel_name: Mapped[str] = mapped_column(
        String(255), default="", server_default="", nullable=False, comment="酒店名称默认值"
    )
    rate_hexiao: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.9000"), server_default=text("0.9000"),
        nullable=False, comment="景区核销率默认值",
    )
    rate_settle: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.9400"), server_default=text("0.9400"),
        nullable=False, comment="结算费率默认值",
    )
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.0600"), server_default=text("0.0600"),
        nullable=False, comment="服务商佣金率默认值(仅抖音)",
    )
    hotel_fee_algo: Mapped[int] = mapped_column(
        SmallInteger().with_variant(TINYINT(unsigned=True), "mysql"),
        default=1, server_default=text("1"), nullable=False,
        comment="酒店服务费算法(1=间夜算法;2=结算费率算法)",
    )
    fee_per_night: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("44.00"), server_default=text("44.00"),
        nullable=False, comment="每间夜服务费默认值",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1"), nullable=False, comment="是否启用台账配置"
    )
