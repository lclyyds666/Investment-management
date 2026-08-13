"""审批相关 schema（含电子签章与审计字段）。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.enums import ApprovalAction, role_label


class ApproveRequest(BaseModel):
    """通过：审批意见可选。"""

    comment: str = ""


class RejectRequest(BaseModel):
    """驳回：原因必填。"""

    comment: str = Field(min_length=1, description="驳回原因（必填）")

    @field_validator("comment")
    @classmethod
    def require_nonblank_comment(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("退回原因不能为空")
        return normalized


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
    organization_code: Optional[str] = None
    organization_name: Optional[str] = None
    position_code: Optional[str] = None
    position_name: Optional[str] = None
    created_at: datetime

    @computed_field
    @property
    def role_label(self) -> str:
        return self.position_name or role_label(self.approver_role)
