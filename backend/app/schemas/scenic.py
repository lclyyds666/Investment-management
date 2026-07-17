"""文旅业务·景区核销台账 schema。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ScenicLedgerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenic_id: str
    row_no: int = 0
    data: dict
    source_file: str = ""
    created_at: Optional[datetime] = None


class ScenicLedgerOut(BaseModel):
    """台账查询结果：列头 + 行数据（前端据此渲染预览表格）。"""

    scenic_id: str
    columns: list[str] = []
    rows: list[ScenicLedgerRow] = []
    total: int = 0


class ScenicUploadResult(BaseModel):
    scenic_id: str
    inserted: int = 0
    columns: list[str] = []
    source_file: str = ""
