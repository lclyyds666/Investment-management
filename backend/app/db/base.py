"""SQLAlchemy 声明式基类。

所有 ORM 模型继承 Base；在 Alembic / create_all 前
统一在此 import 各模型，确保元数据被注册。
"""
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """带审计时间字段的公共基类。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )


# # 在此处导入全部模型，确保 create_all / Alembic 能发现元数据。
# from app.models.user import User  # noqa: E402,F401
# from app.models.contract import Contract  # noqa: E402,F401
# from app.models.approval import Approval  # noqa: E402,F401
# from app.models.operation import OperationData  # noqa: E402,F401
