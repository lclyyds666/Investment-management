"""审批单相关 schema（审批中心两套工作流）。"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.enums import (
    CONTRACT_STATUS_LABELS,
    CONTRACT_TYPE_LABELS,
    ApprovalAction,
    ContractStatus,
    ContractType,
    form_role_at_step,
    role_label,
)


class ApprovalFormBase(BaseModel):
    form_type: ContractType
    department: str = ""
    apply_date: Optional[date] = None
    customer_id: Optional[int] = None
    customer_name: str = ""
    business_type: str = ""
    business_desc: str = "详见合同"
    contract_no: str = ""
    remark: str = ""
    # 付款审批单专有（业务审批单忽略）
    amount: Decimal = Decimal("0")
    bank_name: str = ""
    bank_account: str = ""

    @field_validator(
        "department", "customer_name", "business_type", "business_desc",
        "contract_no", "remark", "bank_name", "bank_account",
        mode="before",
    )
    @classmethod
    def _none_to_empty(cls, v):
        return "" if v is None else v


class ApprovalFormCreate(ApprovalFormBase):
    pass


class ApprovalFormUpdate(BaseModel):
    department: Optional[str] = None
    apply_date: Optional[date] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    business_type: Optional[str] = None
    business_desc: Optional[str] = None
    contract_no: Optional[str] = None
    remark: Optional[str] = None
    amount: Optional[Decimal] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None


class ApprovalFormOut(ApprovalFormBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount_words: str = ""
    attachment_name: str = ""
    status: ContractStatus
    current_step: int = 0
    created_by: int
    creator_name: str = ""  # 由端点补充
    created_at: Optional[datetime] = None

    @computed_field
    @property
    def form_type_label(self) -> str:
        return CONTRACT_TYPE_LABELS.get(self.form_type.value, self.form_type.value)

    @computed_field
    @property
    def status_label(self) -> str:
        return CONTRACT_STATUS_LABELS.get(self.status.value, self.status.value)

    @computed_field
    @property
    def current_role(self) -> Optional[str]:
        if self.status != ContractStatus.PENDING:
            return None
        r = form_role_at_step(self.form_type, self.current_step)
        return r.value if r else None

    @computed_field
    @property
    def current_role_label(self) -> Optional[str]:
        if self.status != ContractStatus.PENDING:
            return None
        r = form_role_at_step(self.form_type, self.current_step)
        return r.label if r else None


class ApprovalFormActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    form_id: int
    approver_id: int
    approver_name: str = ""
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


class ApproveRequest(BaseModel):
    comment: str = ""


class RejectRequest(BaseModel):
    comment: str = Field(min_length=1, description="驳回原因（必填）")
