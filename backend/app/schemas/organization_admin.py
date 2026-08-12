from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.enums import AssignmentStatus, CompanyCode, DataScope, OrganizationType, PositionCategory


GOVERNANCE_POSITION_TARGETS = {
    "governance.supply_leader": "supplymanagement",
    "governance.fund_leader": "fundmanagement",
}


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

    @model_validator(mode="after")
    def normalize_external_detail(self):
        self.provider_name = self.provider_name.strip()
        self.service_scopes = [scope.strip() for scope in self.service_scopes]
        if not self.provider_name or not self.service_scopes or any(not scope for scope in self.service_scopes):
            raise ValueError("External assignment requires a provider and nonblank service scopes.")
        return self


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
        target_company = GOVERNANCE_POSITION_TARGETS.get(self.position_code)
        if target_company is not None and not any(
            scope.scope_type == "company" and scope.scope_ref == target_company
            for scope in self.governance_scopes
        ):
            raise ValueError("Governance assignments require a scope for their target subsidiary.")
        if self.position_code == "external.legal_counsel":
            if (
                self.external is None
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
