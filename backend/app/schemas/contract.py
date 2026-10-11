"""合同相关 schema。"""
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.enums import (
    CONTRACT_STATUS_LABELS,
    ContractStatus,
)


class ContractBase(BaseModel):
    title: str
    party_a: str = ""
    party_b: str = ""
    amount: Decimal = Decimal("0")
    sign_date: Optional[date] = None
    remark: str = ""
    # 审批单业务字段
    contract_type: str = ""          # 合同类型：改为手动输入的自由文本
    department: str = ""
    customer_name: str = ""
    customer_credit_code: str = ""   # 客户统一社会信用代码（选客户时联动填充）
    business_type: str = ""
    # 合同全生命周期新增字段
    is_internal: bool = False
    subject: str = ""
    currency: str = "人民币"
    payment_terms: str = ""
    contract_term: str = ""

    # 兼容历史数据：迁移新增的可空列在旧行为 NULL，
    # 序列化为 ContractOut 时按空串处理，避免 string_type 校验 500。
    @field_validator(
        "party_a", "party_b", "remark", "contract_type", "department", "customer_name",
        "customer_credit_code", "business_type", "subject", "currency", "payment_terms",
        "contract_term",
        mode="before",
    )
    @classmethod
    def _none_to_empty_str(cls, v):
        return "" if v is None else v


class ContractCreate(ContractBase):
    contract_no: str
    scenic_id: str
    business_scopes: list[str]
    initiator_assignment_id: Optional[int] = None
    organization_code: Optional[str] = None

    @field_validator("scenic_id")
    @classmethod
    def validate_scenic_id(cls, value):
        normalized = value.strip()
        if not normalized:
            raise ValueError("必须选择所属景区")
        return normalized

    @field_validator("business_scopes")
    @classmethod
    def validate_business_scopes(cls, value):
        normalized = list(dict.fromkeys(value))
        if not normalized or not set(normalized) <= {"ticket", "hotel"}:
            raise ValueError("业务范围只能选择门票或酒店，且至少选择一项")
        return normalized


class ContractUpdate(BaseModel):
    title: Optional[str] = None
    party_a: Optional[str] = None
    party_b: Optional[str] = None
    amount: Optional[Decimal] = None
    sign_date: Optional[date] = None
    remark: Optional[str] = None
    contract_type: Optional[str] = None
    department: Optional[str] = None
    customer_name: Optional[str] = None
    customer_credit_code: Optional[str] = None
    business_type: Optional[str] = None
    is_internal: Optional[bool] = None
    subject: Optional[str] = None
    currency: Optional[str] = None
    payment_terms: Optional[str] = None
    contract_term: Optional[str] = None
    scenic_id: Optional[str] = None
    business_scopes: Optional[list[str]] = None

    @field_validator("scenic_id")
    @classmethod
    def validate_scenic_id(cls, value):
        if value is None:
            raise ValueError("必须选择所属景区")
        normalized = value.strip()
        if not normalized:
            raise ValueError("必须选择所属景区")
        return normalized

    @field_validator("business_scopes")
    @classmethod
    def validate_business_scopes(cls, value):
        if value is None:
            raise ValueError("业务范围只能选择门票或酒店，且至少选择一项")
        normalized = list(dict.fromkeys(value))
        if not normalized or not set(normalized) <= {"ticket", "hotel"}:
            raise ValueError("业务范围只能选择门票或酒店，且至少选择一项")
        return normalized


class ContractOut(ContractBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_no: str
    status: ContractStatus
    current_step: int = 0
    created_by: int
    company_code: str
    organization_code: str
    initiator_assignment_id: Optional[int] = None
    workflow_route_version: int = 0
    creator_name: str = ""  # 由端点补充（业务经办姓名）
    attachment_name: str = ""  # 合同附件原始文件名（空表示未上传）
    workflow_instance_id: Optional[int] = None
    workflow_version: Optional[int] = None
    active_task: Optional[dict] = None
    can_act: bool = False
    scenic_id: Optional[str] = None
    business_scopes: list[str] = Field(default_factory=list)

    @field_validator("business_scopes", mode="before")
    @classmethod
    def _business_scopes_none_to_empty_list(cls, value):
        return [] if value is None else value

    @computed_field
    @property
    def status_label(self) -> str:
        return CONTRACT_STATUS_LABELS.get(self.status.value, self.status.value)

    @computed_field
    @property
    def contract_type_label(self) -> str:
        # 合同类型已改为自由文本，直接回显
        return self.contract_type or ""

    @computed_field
    @property
    def current_role(self) -> Optional[str]:
        return self.active_task.get("position_code") if self.active_task else None

    @computed_field
    @property
    def current_role_label(self) -> Optional[str]:
        return self.active_task.get("position_name") if self.active_task else None
