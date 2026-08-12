"""用户相关 Pydantic schema。"""
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.core.config import settings
from app.core.enums import CompanyCode, Role, role_label
from app.schemas.organization import AssignmentOut


class CompanyRoleAssignment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_code: CompanyCode
    role: Role


class UserBase(BaseModel):
    username: str
    full_name: str = ""
    role: Role = Role.BUSINESS_HANDLER
    department: str = ""


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    full_name: str = ""
    password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH)


class UserUpdate(BaseModel):
    """超管编辑用户：不含用户名（登录账号不可改）与密码。"""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    department: str | None = None
    is_active: bool | None = None


class ActiveUpdate(BaseModel):
    is_active: bool


class PasswordReset(BaseModel):
    """超管重置某用户密码；不填则重置为系统默认密码。"""

    new_password: str | None = Field(default=None, min_length=settings.PASSWORD_MIN_LENGTH)


class PasswordChange(BaseModel):
    """用户修改本人密码。"""

    old_password: str
    new_password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH)


class UsernameChange(BaseModel):
    """用户修改本人登录账号(用户名)；需当前密码确认身份。"""

    new_username: str = Field(..., min_length=3, max_length=64)
    password: str


class UserOut(UserBase):
    """当前登录用户 / 详情：含完整签名（本人数据）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_superuser: bool
    company_roles: list[CompanyRoleAssignment] = Field(
        default_factory=list,
        deprecated=True,
    )
    assignment_summaries: list[AssignmentOut] = Field(default_factory=list)
    signature: str | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_assignment_summaries(cls, value):
        if isinstance(value, dict) or not hasattr(value, "assignments"):
            return value
        return {
            "id": value.id,
            "username": value.username,
            "full_name": value.full_name,
            "role": value.role,
            "department": value.department,
            "is_active": value.is_active,
            "is_superuser": value.is_superuser,
            "company_roles": value.company_roles,
            "signature": value.signature,
            "assignment_summaries": _assignment_summaries(value.assignments),
        }

    @computed_field
    @property
    def role_label(self) -> str:
        return role_label(self.role)

    @computed_field
    @property
    def has_signature(self) -> bool:
        return bool(self.signature)


class UserBrief(BaseModel):
    """组织架构列表用：不返回签名内容，仅返回是否已上传。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str = ""
    role: Role
    department: str = ""
    is_active: bool
    is_superuser: bool
    company_roles: list[CompanyRoleAssignment] = Field(
        default_factory=list,
        deprecated=True,
    )
    assignment_summaries: list[AssignmentOut] = Field(default_factory=list)
    # 参与 has_signature 计算，但不序列化到列表输出（避免返回大体积签名）
    signature: str | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def populate_assignment_summaries(cls, value):
        if isinstance(value, dict) or not hasattr(value, "assignments"):
            return value
        return {
            "id": value.id,
            "username": value.username,
            "full_name": value.full_name,
            "role": value.role,
            "department": value.department,
            "is_active": value.is_active,
            "is_superuser": value.is_superuser,
            "company_roles": value.company_roles,
            "signature": value.signature,
            "assignment_summaries": _assignment_summaries(value.assignments),
        }

    @computed_field
    @property
    def role_label(self) -> str:
        return role_label(self.role)

    @computed_field
    @property
    def has_signature(self) -> bool:
        return bool(self.signature)


class SignatureUpdate(BaseModel):
    """纸质签名上传（Mock）：传图片的 data-URI 或附件路径。"""

    signature: str


def _assignment_summaries(assignments) -> list[dict]:
    return [
        {
            "assignment_id": assignment.id,
            "organization_code": assignment.organization.code,
            "organization_name": assignment.organization.name,
            "position_code": assignment.position.code,
            "position_name": assignment.position.name,
            "valid_from": assignment.valid_from,
            "valid_until": assignment.valid_until,
            "status": assignment.status,
        }
        for assignment in assignments
    ]
