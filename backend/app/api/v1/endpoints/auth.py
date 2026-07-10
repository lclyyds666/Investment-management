"""认证端点：登录、获取当前用户。"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import Token
from app.schemas.user import UserOut

router = APIRouter()


@router.post("/auth/login", response_model=Token, summary="登录获取令牌")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """使用 OAuth2 表单(username/password)登录，返回 JWT。

    兼容 Swagger 的 Authorize 按钮，前端也可直接以 form 形式提交。
    """
    user = db.scalar(select(User).where(User.username == form_data.username))
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    token = create_access_token(subject=user.id, role=user.role.value)
    return Token(
        access_token=token,
        role=user.role,
        user=UserOut.model_validate(user),
    )


@router.get("/auth/me", response_model=UserOut, summary="获取当前登录用户")
def read_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
