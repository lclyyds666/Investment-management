"""FastAPI 依赖：认证与基于角色的权限控制(RBAC)。"""
from typing import Iterable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import Role
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

# tokenUrl 用于 Swagger 的 Authorize 按钮
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录已失效或令牌无效",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise credentials_exc

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise credentials_exc
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return user


def require_roles(*roles: Role):
    """生成一个依赖：要求当前用户角色在允许列表内。

    超级管理员(is_superuser)始终放行。用法::

        @router.get("/x", dependencies=[Depends(require_roles(Role.LEADER))])
    """
    allowed: Iterable[Role] = roles

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.is_superuser:
            return current_user
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，无法访问该资源",
            )
        return current_user

    return checker


def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    """要求当前用户为超级管理员。用户管理等敏感操作使用。"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可执行该操作",
        )
    return current_user
