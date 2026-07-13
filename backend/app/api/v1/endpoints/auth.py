"""认证端点：图形验证码、登录（含防爆破）、获取当前用户。"""
from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import CaptchaOut, Token
from app.schemas.user import UserOut
from app.services import captcha, login_guard

router = APIRouter()


@router.get("/auth/captcha", response_model=CaptchaOut, summary="获取图形验证码")
def get_captcha():
    """生成一枚图形验证码，返回 captcha_id 与 SVG 图片(data-URI)。

    前端登录时需回传 captcha_id + 用户填写的字符；验证码一次性使用、有过期时间。
    """
    captcha_id, image = captcha.generate()
    return CaptchaOut(captcha_id=captcha_id, image=image, ttl=settings.CAPTCHA_TTL_SECONDS)


@router.post("/auth/login", response_model=Token, summary="登录获取令牌")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    captcha_id: str | None = Form(default=None, description="图形验证码ID"),
    captcha_code: str | None = Form(default=None, description="图形验证码字符"),
    db: Session = Depends(get_db),
):
    """OAuth2 表单登录，返回 JWT。

    安全加固：
    - **图形验证码**：``CAPTCHA_ENABLED`` 开启时必填且校验（防自动化撞库）；
    - **暴力破解防护**：连续失败 ``LOGIN_MAX_FAILURES`` 次锁定 ``LOGIN_LOCK_MINUTES`` 分钟。
    """
    username = form_data.username

    # 1) 锁定检查：锁定窗口内一律拒绝（即便密码正确）
    remaining = login_guard.lock_remaining_seconds(username)
    if remaining > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"账号已锁定，请 {remaining // 60 + 1} 分钟后再试",
        )

    # 2) 图形验证码校验（先于密码，避免无验证码的自动化尝试消耗计数）
    if settings.CAPTCHA_ENABLED:
        if not captcha.verify(captcha_id, captcha_code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="验证码错误或已过期，请刷新后重试",
            )

    # 3) 账号密码校验
    user = db.scalar(select(User).where(User.username == username))
    if not user or not verify_password(form_data.password, user.hashed_password):
        count = login_guard.record_failure(username)
        left = max(0, settings.LOGIN_MAX_FAILURES - count)
        if left <= 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"失败次数过多，账号已锁定 {settings.LOGIN_LOCK_MINUTES} 分钟",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"账号或密码错误，还可尝试 {left} 次",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    # 4) 成功：清除失败计数，签发令牌
    login_guard.clear(username)
    token = create_access_token(subject=user.id, role=user.role.value)
    return Token(
        access_token=token,
        role=user.role,
        user=UserOut.model_validate(user),
    )


@router.get("/auth/me", response_model=UserOut, summary="获取当前登录用户")
def read_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
