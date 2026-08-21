"""投资公司法务风控 API schema。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.legal_risk import (
    LegalAlertStatus,
    LegalAlertType,
    LegalCaseStage,
    LegalCaseStatus,
    LegalCollaboratorType,
    LegalDeadlineType,
    LegalJudgmentType,
    LegalPartyType,
    LegalProgressType,
    LegalRecoveryType,
)

T = TypeVar("T")


class LegalPage(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class LegalCaseBase(BaseModel):
    case_name: str = Field(min_length=1, max_length=255)
    cause_of_action: str = ""
    court: str = ""
    court_case_no: str = ""
    subject_amount: Decimal = Field(default=Decimal("0"), ge=0)
    responsible_user_id: int | None = None
    confidentiality_level: str = "internal"
    law_firm: str = ""
    attorney_name: str = ""
    case_summary: str = ""
    claims: str = ""
    enforcement_property_status: str = ""


class LegalCaseCreate(LegalCaseBase):
    responsible_user_name: str | None = Field(default=None, max_length=64, exclude=True)
    initiator_assignment_id: int | None = None
    organization_code: str | None = None


class LegalCaseUpdate(BaseModel):
    version: int = Field(ge=1)
    case_name: str | None = Field(default=None, min_length=1, max_length=255)
    cause_of_action: str | None = None
    court: str | None = None
    court_case_no: str | None = None
    subject_amount: Decimal | None = Field(default=None, ge=0)
    responsible_user_id: int | None = None
    responsible_user_name: str | None = Field(default=None, max_length=64, exclude=True)
    confidentiality_level: str | None = None
    law_firm: str | None = None
    attorney_name: str | None = None
    case_summary: str | None = None
    claims: str | None = None
    enforcement_property_status: str | None = None
    closed_date: date | None = None
    closure_summary: str | None = None

    @model_validator(mode="after")
    def reject_null_for_non_nullable_fields(self):
        non_nullable = {
            "case_name", "cause_of_action", "court", "court_case_no", "subject_amount",
            "confidentiality_level", "law_firm", "attorney_name", "case_summary",
            "claims", "enforcement_property_status", "closure_summary",
        }
        invalid = [name for name in non_nullable if name in self.model_fields_set and getattr(self, name) is None]
        if invalid:
            raise ValueError(f"字段不能为 null：{', '.join(sorted(invalid))}")
        return self


class LegalCaseStatusUpdate(BaseModel):
    status: LegalCaseStatus
    version: int = Field(ge=1)
    terminal_date: date | None = None


class LegalArchiveIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class LegalUnarchiveIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class LegalCaseOut(LegalCaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_code: str
    organization_code: str
    initiator_assignment_id: int | None
    company_name: str = ""
    organization_name: str = ""
    stage: LegalCaseStage
    case_no: str | None
    status: LegalCaseStatus | None
    version: int
    terminal_date: date | None
    closed_date: date | None
    closure_summary: str
    archived_at: datetime | None
    archive_note: str
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LegalInitiatorOptionOut(BaseModel):
    assignment_id: int
    company_code: str
    company_name: str
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str


class LegalPartyIn(BaseModel):
    party_type: LegalPartyType
    name: str = Field(min_length=1, max_length=255)
    identity_type: str = "organization"
    identity_no: str = ""
    contact: str = ""
    address: str = ""
    sort_order: int = 0


class LegalPartyOut(LegalPartyIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class LegalCollaboratorIn(BaseModel):
    user_id: int | None = None
    user_name: str | None = Field(default=None, max_length=64, exclude=True)
    collaborator_type: LegalCollaboratorType
    expires_at: datetime | None = None


class LegalCollaboratorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    collaborator_type: LegalCollaboratorType
    expires_at: datetime | None = None
    effective_at: datetime


class LegalJudgmentIn(BaseModel):
    judgment_type: LegalJudgmentType
    summary: str = ""
    judgment_date: date | None = None
    effective_date: date | None = None
    performance_deadline: date | None = None
    executable_amount: Decimal | None = Field(default=None, ge=0)
    is_current_enforcement_basis: bool = False
    sort_order: int = 0


class LegalJudgmentOut(LegalJudgmentIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class LegalAssetIn(BaseModel):
    asset_type: str = Field(min_length=1, max_length=64)
    asset_name: str = Field(min_length=1, max_length=500)
    measure_type: str = Field(min_length=1, max_length=64)
    priority_type: str = ""
    start_date: date | None = None
    expiry_date: date | None = None
    reminder_days: int | None = Field(default=None, ge=0, le=365)
    disposal_status: str = ""
    notes: str = ""


class LegalAssetOut(LegalAssetIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    remaining_days: int | None = None


class LegalRecoveryIn(BaseModel):
    recovery_type: LegalRecoveryType
    recovery_date: date
    amount: Decimal = Field(gt=0)
    source_description: str = ""


class LegalRecoveryOut(LegalRecoveryIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class LegalProgressIn(BaseModel):
    progress_type: LegalProgressType
    content: str = Field(min_length=1)
    risk_points: str = ""
    next_plan: str = ""
    responsible_user_id: int | None = None
    planned_date: date | None = None


class LegalProgressOut(LegalProgressIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    registered_by: int
    recorded_at: datetime


class LegalDeadlineIn(BaseModel):
    deadline_type: LegalDeadlineType
    title: str = Field(min_length=1, max_length=255)
    event_date: date
    reminder_days: int | None = Field(default=None, ge=0, le=365)
    responsible_user_id: int | None = None


class LegalDeadlineOut(LegalDeadlineIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_completed: bool
    completed_at: datetime | None
    completion_note: str


class LegalCompletionIn(BaseModel):
    result: str = Field(min_length=1, max_length=2000)


class LegalMoneySummary(BaseModel):
    subject_amount: Decimal
    executable_amount: Decimal | None
    recovered_amount: Decimal
    avoided_loss_amount: Decimal
    outstanding_amount: Decimal


class LegalCaseDetailOut(LegalCaseOut):
    parties: list[LegalPartyOut]
    collaborators: list[LegalCollaboratorOut]
    judgments: list[LegalJudgmentOut]
    assets: list[LegalAssetOut]
    recoveries: list[LegalRecoveryOut]
    progress_records: list[LegalProgressOut]
    deadlines: list[LegalDeadlineOut]
    money: LegalMoneySummary


class LegalAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    alert_type: LegalAlertType
    trigger_date: date
    due_date: date
    level: str
    responsible_user_id: int | None
    status: LegalAlertStatus
    result: str


class LegalAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    related_type: str
    related_id: int | None
    category: str
    original_name: str
    extension: str
    mime_type: str
    size_bytes: int
    sha256: str
    uploaded_by: int
    created_at: datetime


class LegalAlertActionIn(BaseModel):
    result: str = Field(min_length=1, max_length=2000)


class LegalImportConfirmIn(BaseModel):
    confirmed_warning_rows: list[int] = Field(default_factory=list)
    initiator_assignment_id: int | None = None
    organization_code: str | None = None

    @field_validator("confirmed_warning_rows")
    @classmethod
    def unique_rows(cls, value: list[int]) -> list[int]:
        return sorted(set(value))
