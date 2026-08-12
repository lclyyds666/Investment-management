from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.enums import AssignmentStatus, CompanyCode, DataScope, OrganizationType, PositionCategory


class OrganizationWrite(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    organization_type: OrganizationType
    parent_code: str | None = None
    company_code: CompanyCode | None = None
    sort_order: int = 0
    is_active: bool = True


class PositionWrite(BaseModel):
    code: str = Field(min_length=3, max_length=96)
    name: str = Field(min_length=1, max_length=128)
    category: PositionCategory
    is_active: bool = True


class PositionPermissionWrite(BaseModel):
    permission_code: str
    data_scope: DataScope
    scope_ref: str = ""


class GovernanceScopeWrite(BaseModel):
    scope_type: Literal["company", "department", "business_domain"]
    scope_ref: str


class ExternalAssignmentWrite(BaseModel):
    provider_name: str
    service_scopes: list[str]


class AssignmentWrite(BaseModel):
    organization_code: str
    position_code: str
    valid_from: date
    valid_until: date | None = None
    status: AssignmentStatus = AssignmentStatus.ACTIVE
    governance_scopes: list[GovernanceScopeWrite] = Field(default_factory=list)
    external: ExternalAssignmentWrite | None = None

    @model_validator(mode="after")
    def validate_assignment(self):
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("Assignment end date cannot precede its start date.")
        if self.position_code == "external.legal_counsel":
            if (
                self.external is None
                or not self.external.provider_name.strip()
                or not self.external.service_scopes
                or self.valid_until is None
            ):
                raise ValueError(
                    "External legal counsel requires an end date, provider, and service scopes."
                )
        elif self.external is not None:
            raise ValueError("External assignment detail is only valid for external legal counsel.")
        return self


class UserAssignmentsReplace(BaseModel):
    assignments: list[AssignmentWrite]

    @model_validator(mode="after")
    def reject_duplicates(self):
        identities = [
            (item.organization_code, item.position_code, item.valid_from, item.valid_until)
            for item in self.assignments
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate assignment rows are not allowed.")
        return self
