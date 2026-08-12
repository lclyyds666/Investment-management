"""统一门户应用与当前用户权限快照响应模型。"""
from datetime import date

from pydantic import BaseModel, Field


class PortalApplicationOut(BaseModel):
    code: str
    company_name: str
    route: str
    status: str
    accessible: bool
    denial_reason: str | None = None


class AssignmentSnapshotOut(BaseModel):
    assignment_id: int
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str
    valid_from: date
    valid_until: date | None


class PermissionGrantOut(BaseModel):
    code: str
    data_scope: str
    scope_ref: str


class PortalPermissionSnapshot(BaseModel):
    is_superuser: bool
    assignments: list[AssignmentSnapshotOut]
    permissions: list[PermissionGrantOut]
    resources: list[str]
    company_roles: dict[str, str] = Field(
        default_factory=dict,
        deprecated="frontend compatibility only",
    )
