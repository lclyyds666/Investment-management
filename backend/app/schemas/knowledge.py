"""法规知识库 schema。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeDocOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str = "法律规范"
    filename: str = ""
    file_type: str = ""
    char_count: int = 0
    uploaded_by: str = ""
    created_at: datetime
