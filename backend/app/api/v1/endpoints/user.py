"""用户 / 组织架构端点：电子签名资产管理与人员列表。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Response
from app.schemas.user import SignatureUpdate, UserBrief, UserOut

router = APIRouter()


@router.get("/me", response_model=Response[UserOut], summary="当前用户资料(含签名)")
def get_me(current_user: User = Depends(get_current_user)):
    return Response.ok(UserOut.model_validate(current_user))


@router.put(
    "/me/signature",
    response_model=Response[UserOut],
    summary="上传/更新本人纸质签名(Mock)",
)
def update_my_signature(
    payload: SignatureUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将签名图片（data-URI 或附件路径）保存为该员工的核心签章资产。"""
    current_user.signature = payload.signature
    db.commit()
    db.refresh(current_user)
    return Response.ok(UserOut.model_validate(current_user))


@router.get("", response_model=Response[list[UserBrief]], summary="组织架构 / 人员列表")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按审批链角色排序展示人员（不含签名内容，仅标记是否已上传）。"""
    rows = db.scalars(select(User).order_by(User.id.asc())).all()
    return Response.ok([UserBrief.model_validate(u) for u in rows])
