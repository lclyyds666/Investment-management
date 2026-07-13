"""认证相关 schema。"""
from pydantic import BaseModel

from app.core.enums import Role
from app.schemas.user import UserOut


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    user: UserOut


class TokenPayload(BaseModel):
    sub: str | None = None
    role: str | None = None


class CaptchaOut(BaseModel):
    """图形验证码：captcha_id 关联答案，image 为 SVG data-URI。"""

    captcha_id: str
    image: str
    ttl: int
