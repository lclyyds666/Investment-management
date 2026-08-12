"""统一门户应用与当前用户权限快照响应模型。"""
from pydantic import BaseModel


class PortalApplicationOut(BaseModel):
    code: str
    company_name: str
    route: str
    status: str
    accessible: bool
    denial_reason: str | None = None


class PortalPermissionSnapshot(BaseModel):
    is_superuser: bool
    company_roles: dict[str, str]
    resources: list[str]
