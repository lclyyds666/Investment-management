"""用户相关 Pydantic schema。"""
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.core.config import settings
from app.core.enums import CompanyCode, Role, role_label


class CompanyRoleAssignment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_code: CompanyCode
    role: Role


def _validate_unique_companies(assignments: list[CompanyRoleAssignment] | None) -> None:
    if assignments is None:
        return
    company_codes = [assignment.company_code for assignment in assignments]
    if len(company_codes) != len(set(company_codes)):
        raise ValueError("同一公司只能分配一个角色")


def _validate_admin_identity(role: Role, is_superuser: bool) -> None:
    if (role == Role.INFO_MAINTAINER) != is_superuser:
        raise ValueError("信息维护与超级管理员必须是同一个角色和账号身份")


class UserBase(BaseModel):
    username: str
    full_name: str = ""
    role: Role = Role.BUSINESS_HANDLER
    department: str = ""


class UserCreate(UserBase):
    password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH)
    is_superuser: bool = False
    company_roles: list[CompanyRoleAssignment] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_company_roles_and_identity(self):
        _validate_unique_companies(self.company_roles)
        _validate_admin_identity(self.role, self.is_superuser)
        return self


class UserUpdate(BaseModel):
    """超管编辑用户：不含用户名（登录账号不可改）与密码。"""

    full_name: str | None = None
    role: Role | None = None
    department: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    company_roles: list[CompanyRoleAssignment] | None = None

    @model_validator(mode="after")
    def validate_company_roles_and_identity(self):
        _validate_unique_companies(self.company_roles)
        if self.role is not None and self.is_superuser is not None:
            _validate_admin_identity(self.role, self.is_superuser)
        return self


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
    company_roles: list[CompanyRoleAssignment] = Field(default_factory=list)
    signature: str | None = None

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
    company_roles: list[CompanyRoleAssignment] = Field(default_factory=list)
    # 参与 has_signature 计算，但不序列化到列表输出（避免返回大体积签名）
    signature: str | None = Field(default=None, exclude=True)

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
