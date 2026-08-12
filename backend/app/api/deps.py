"""FastAPI 依赖：认证与基于角色的权限控制(RBAC)。"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import CompanyCode, ResourceCode, Role
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.assignment_permissions import PermissionContext, has_permission, has_position
from app.services.legacy_assignment_migration import LEGACY_TARGETS
from app.services.permissions import has_resource

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
    """Temporary adapter requiring one of the mapped active positions.

    用法::

        @router.get("/x", dependencies=[Depends(require_roles(Role.LEADER))])
    """
    position_codes = tuple(
        LEGACY_TARGETS[role].position_code
        for role in roles
        if role in LEGACY_TARGETS
    )

    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not any(has_position(db, current_user.id, code) for code in position_codes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，无法访问该资源",
            )
        return current_user

    return checker


def require_permission(permission_code: str, context_factory=None):
    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        context = context_factory() if context_factory else PermissionContext()
        if not has_permission(db, current_user, permission_code, context):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return current_user

    return checker


def require_company_resource(company: CompanyCode, resource: ResourceCode):
    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not has_resource(db, current_user, company, resource):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return current_user

    return checker


def require_any_company_resource(company: CompanyCode, *resources: ResourceCode):
    if not resources:
        raise ValueError("at least one resource is required")

    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not any(has_resource(db, current_user, company, resource) for resource in resources):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
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
