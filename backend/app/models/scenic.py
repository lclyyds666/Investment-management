"""文旅业务·景区核销数据台账模型。

严格数据隔离：每条台账行都带 scenic_id（景区作用域键），所有读写按 scenic_id 过滤，
scenic_id 一律取自 URL 路径，不信任客户端请求体，接口绝不跨景区返回数据。
"""
from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScenicLedger(Base):
    __tablename__ = "biz_scenic_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    # 景区作用域键：数据隔离的核心，建索引加速按景区过滤
    scenic_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="景区ID(作用域键)"
    )
    row_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="行序(用于稳定排序)")
    data: Mapped[dict] = mapped_column(JSON, nullable=False, comment="单行核销数据(列名→值)")
    source_file: Mapped[str] = mapped_column(String(255), default="", comment="来源Excel文件名")
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id"), nullable=True, comment="上传人"
    )
