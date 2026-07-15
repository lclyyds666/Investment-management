"""合同相关 schema。"""
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from app.core.enums import (
    CONTRACT_STATUS_LABELS,
    ContractStatus,
    role_at_step,
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

    # 兼容历史数据：迁移新增的可空列在旧行为 NULL，
    # 序列化为 ContractOut 时按空串处理，避免 string_type 校验 500。
    @field_validator(
        "party_a", "party_b", "remark", "contract_type", "department", "customer_name",
        "customer_credit_code", "business_type", "subject", "currency", "payment_terms",
        mode="before",
    )
    @classmethod
    def _none_to_empty_str(cls, v):
        return "" if v is None else v


class ContractCreate(ContractBase):
    contract_no: str


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


class ContractOut(ContractBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_no: str
    status: ContractStatus
    current_step: int = 0
    created_by: int
    creator_name: str = ""  # 由端点补充（业务经办姓名）
    attachment_name: str = ""  # 合同附件原始文件名（空表示未上传）

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
        """审批中的合同：当前待审批角色值；否则 None。"""
        if self.status != ContractStatus.PENDING:
            return None
        r = role_at_step(self.current_step)
        return r.value if r else None

    @computed_field
    @property
    def current_role_label(self) -> Optional[str]:
        if self.status != ContractStatus.PENDING:
            return None
        r = role_at_step(self.current_step)
        return r.label if r else None
