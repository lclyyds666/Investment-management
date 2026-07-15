"""客户档案模型（主数据管理）。"""
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Customer(Base):
    __tablename__ = "biz_customer"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    customer_code: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="客户ID/编码"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="客户名称")
    social_credit_code: Mapped[str] = mapped_column(String(32), default="", comment="统一社会信用代码")
    address: Mapped[str] = mapped_column(String(255), default="", comment="地址")
    contact: Mapped[str] = mapped_column(String(64), default="", comment="联系人")
    phone: Mapped[str] = mapped_column(String(32), default="", comment="电话")
    # 准入资料附件（Mock）：[{name, url}]
    admission_files: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="准入资料附件")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")
