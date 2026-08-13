from datetime import date

from pydantic import BaseModel

from app.core.enums import AssignmentStatus, DataScope


class AssignmentOut(BaseModel):
    assignment_id: int
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str
    valid_from: date
    valid_until: date | None
    status: AssignmentStatus


class EffectivePermissionOut(BaseModel):
    code: str
    data_scope: DataScope
    scope_ref: str
