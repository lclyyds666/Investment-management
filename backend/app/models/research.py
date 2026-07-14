"""客户 AI 尽职调查相关模型：上传的准入资料 + 生成的调研报告。

- CustomerMaterial：一份上传的准入资料（PDF/Docx）解析后的逐页文本 + 关键信息，
  原始文件另存服务器磁盘（stored_name 指向 UPLOAD_DIR 下的文件）。
- CustomerResearch：一次《尽职调查报告》的结构化结果（四段 + 合作建议 + 来源）。
"""
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerMaterial(Base):
    __tablename__ = "biz_customer_material"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    customer_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False, comment="客户ID")
    filename: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    stored_name: Mapped[str] = mapped_column(String(255), default="", comment="磁盘存储名(UPLOAD_DIR下)")
    file_type: Mapped[str] = mapped_column(String(16), default="", comment="pdf/docx")
    page_count: Mapped[int] = mapped_column(Integer, default=0, comment="页数")
    char_count: Mapped[int] = mapped_column(Integer, default=0, comment="提取字符数")
    pages: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="逐页文本[{page,text}]")
    key_info: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="正则抽取的关键信息")
    uploaded_by: Mapped[str] = mapped_column(String(64), default="", comment="上传人")


class CustomerResearch(Base):
    __tablename__ = "biz_customer_research"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    customer_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False, comment="客户ID")
    recommendation: Mapped[str] = mapped_column(
        String(16), default="", comment="合作建议：优先合作/谨慎合作/严禁合作"
    )
    sections: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="四段报告{basic,operation,sentiment,risk,key_risks}"
    )
    report_md: Mapped[str] = mapped_column(Text, default="", comment="渲染后的 Markdown 报告全文")
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="信息来源[{type,title,ref}]")
    engine: Mapped[str] = mapped_column(String(16), default="", comment="deepseek/rule")
    searched: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否成功联网检索")
    search_count: Mapped[int] = mapped_column(Integer, default=0, comment="外部资讯条数")
    created_by: Mapped[str] = mapped_column(String(64), default="", comment="生成人")
