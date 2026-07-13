"""用户相关 Pydantic schema。"""
from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.config import settings
from app.core.enums import Role, role_label


class UserBase(BaseModel):
    username: str
    full_name: str = ""
    role: Role = Role.BUSINESS_HANDLER
    department: str = ""


class UserCreate(UserBase):
    password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH)
    is_superuser: bool = False


class UserUpdate(BaseModel):
    """超管编辑用户：不含用户名（登录账号不可改）与密码。"""

    full_name: str | None = None
    role: Role | None = None
    department: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None


class ActiveUpdate(BaseModel):
    is_active: bool


class PasswordReset(BaseModel):
    """超管重置某用户密码；不填则重置为系统默认密码。"""

    new_password: str | None = Field(default=None, min_length=settings.PASSWORD_MIN_LENGTH)


class PasswordChange(BaseModel):
    """用户修改本人密码。"""

    old_password: str
    new_password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH)


class UserOut(UserBase):
    """当前登录用户 / 详情：含完整签名（本人数据）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_superuser: bool
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
