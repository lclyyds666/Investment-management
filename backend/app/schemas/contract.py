"""合同相关 schema。"""
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.core.enums import (
    CONTRACT_STATUS_LABELS,
    CONTRACT_TYPE_LABELS,
    ContractStatus,
    ContractType,
    role_at_step,
    role_label,
)


class ContractBase(BaseModel):
    title: str
    party_a: str = ""
    party_b: str = ""
    amount: Decimal = Decimal("0")
    sign_date: Optional[date] = None
    remark: str = ""
    # 审批单业务字段
    contract_type: ContractType = ContractType.PAYMENT
    department: str = ""
    customer_name: str = ""
    business_type: str = ""
    # 合同全生命周期新增字段
    is_internal: bool = False
    subject: str = ""
    currency: str = "人民币"
    payment_terms: str = ""


class ContractCreate(ContractBase):
    contract_no: str


class ContractUpdate(BaseModel):
    title: Optional[str] = None
    party_a: Optional[str] = None
    party_b: Optional[str] = None
    amount: Optional[Decimal] = None
    sign_date: Optional[date] = None
    remark: Optional[str] = None
    contract_type: Optional[ContractType] = None
    department: Optional[str] = None
    customer_name: Optional[str] = None
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
        return CONTRACT_TYPE_LABELS.get(self.contract_type.value, self.contract_type.value)

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
