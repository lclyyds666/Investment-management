"""用户模型（含组织架构与电子签名资产）。"""
from sqlalchemy import Boolean, Enum as SAEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Role
from app.db.base import Base


class User(Base):
    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    username: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="登录账号"
    )
    full_name: Mapped[str] = mapped_column(String(64), default="", comment="姓名")
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False, comment="密码哈希")
    role: Mapped[Role] = mapped_column(
        # 7 级角色，值以字符串存储；length 需容纳最长角色值（investment 等）
        SAEnum(Role, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e]),
        default=Role.BUSINESS_HANDLER,
        nullable=False,
        comment="角色（7 级权限）",
    )
    department: Mapped[str] = mapped_column(String(64), default="", comment="所属部门")
    # 纸质签名图片（Mock：存 data-URI 或附件路径），审批时作为电子签章附加
    signature: Mapped[str | None] = mapped_column(Text, nullable=True, comment="电子签名(图片data-uri或路径)")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否超级管理员")
