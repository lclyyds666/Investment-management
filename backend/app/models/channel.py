"""多渠道数据集成模型。

- Channel：外部平台卡片（含快捷登录账号/密码，Mock 明文用于演示复制）。
- ChannelData：某渠道回传导入的表格数据（列 + 行，JSON 存储，可编辑）。
"""
from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Channel(Base):
    __tablename__ = "biz_channel"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="平台名称")
    biz_type: Mapped[str] = mapped_column(String(16), default="文旅业务", comment="业务类型:文旅业务/其他")
    category: Mapped[str] = mapped_column(String(16), default="other", comment="类别 ticket/hotel/ota/other")
    url: Mapped[str] = mapped_column(String(255), default="", comment="平台地址")
    account: Mapped[str] = mapped_column(String(128), default="", comment="登录账号(Mock)")
    password: Mapped[str] = mapped_column(String(128), default="", comment="登录密码(Mock, 演示明文)")
    logo: Mapped[str] = mapped_column(String(16), default="🔗", comment="图标(emoji)")
    description: Mapped[str] = mapped_column(Text, default="", comment="平台说明")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")

    dataset = relationship("ChannelData", back_populates="channel", uselist=False, cascade="all, delete-orphan")


class ChannelData(Base):
    __tablename__ = "biz_channel_data"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("biz_channel.id", ondelete="CASCADE"), unique=True, index=True, comment="关联渠道"
    )
    columns: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="表头列")
    rows: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="数据行(二维数组)")
    # 列 → 经营指标字段映射：{date_col, revenue_col, cost_col, order_col, business_line}
    # 配置后，回传数据将按此映射汇入 biz_operation_data，联动首页/大屏图表。
    mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="列映射配置")

    channel = relationship("Channel", back_populates="dataset")
