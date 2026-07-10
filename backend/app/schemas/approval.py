"""审批相关 schema（含电子签章与审计字段）。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.enums import ApprovalAction, role_label


class ApproveRequest(BaseModel):
    """通过：审批意见可选。"""

    comment: str = ""


class RejectRequest(BaseModel):
    """驳回：原因必填。"""

    comment: str = Field(min_length=1, description="驳回原因（必填）")


class ApprovalCreate(BaseModel):
    """兼容旧接口：action + comment。"""

    action: ApprovalAction
    comment: str = ""


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_id: int
    approver_id: int
    approver_name: str = ""       # 由端点补充
    step: int = 0
    approver_role: str = ""
    action: ApprovalAction
    comment: str = ""
    signature_snapshot: Optional[str] = None
    created_at: datetime

    @computed_field
    @property
    def role_label(self) -> str:
        return role_label(self.approver_role)
