"""法规知识库模型：存放「公司合同法 / 集团企业制度 / 法律规范」等参考文件。

上传即解析全文入库（content），AI 合同审查时聚合这些文本作为「分析依据」喂给 DeepSeek。
原始文件另存服务器磁盘（stored_name 指向 UPLOAD_DIR/knowledge_base/ 下）。
"""
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 全文可能较大，MySQL 用 MEDIUMTEXT（约 16MB），其他库回退 TEXT
LongText = Text().with_variant(MEDIUMTEXT, "mysql")


class KnowledgeDoc(Base):
    __tablename__ = "biz_knowledge_doc"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="文件标题")
    category: Mapped[str] = mapped_column(
        String(32), default="法律规范", comment="分类：公司合同法/集团企业制度/法律规范/其他"
    )
    filename: Mapped[str] = mapped_column(String(255), default="", comment="原始文件名")
    stored_name: Mapped[str] = mapped_column(String(255), default="", comment="磁盘存储名")
    file_type: Mapped[str] = mapped_column(String(16), default="", comment="pdf/docx/xlsx")
    char_count: Mapped[int] = mapped_column(Integer, default=0, comment="提取字符数")
    content: Mapped[str] = mapped_column(LongText, default="", comment="提取的全文(供 AI 审查引用)")
    uploaded_by: Mapped[str] = mapped_column(String(64), default="", comment="上传人")
