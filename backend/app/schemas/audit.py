"""操作审计 schema。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    username: str = ""
    full_name: str = ""
    role: str = ""
    action: str = ""
    module: str = ""
    target_desc: str = ""
    method: str = ""
    path: str = ""
    ip: str = ""
    status: str = "success"
    http_status: int = 0
    detail: Optional[str] = None
    created_at: Optional[datetime] = None


class AuditLogPage(BaseModel):
    """分页结果。"""

    items: list[AuditLogOut] = []
    total: int = 0
    page: int = 1
    size: int = 20
