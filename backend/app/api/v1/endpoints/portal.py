"""统一门户应用注册表与当前用户权限快照端点。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Response
from app.schemas.portal import PortalApplicationOut, PortalPermissionSnapshot
from app.services.portal import applications_for_user, permission_snapshot_for_user

router = APIRouter()


@router.get(
    "/applications",
    response_model=Response[list[PortalApplicationOut]],
    summary="统一门户应用列表",
)
def get_applications(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return Response.ok(applications_for_user(db, current_user))


@router.get(
    "/me/permissions",
    response_model=Response[PortalPermissionSnapshot],
    summary="当前用户门户权限",
)
def get_my_permissions(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return Response.ok(permission_snapshot_for_user(db, current_user))
