"""用户 / 组织架构端点：完整用户 CRUD（超管）+ 本人资料 / 签名 / 改密。

权限约定：
- ``/me*`` 为本人操作，任意登录用户可用；
- 列表可供负责人 / 超管查看；
- 增删改、重置密码、启停用等敏感操作仅超级管理员（``require_superuser``）。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_superuser
from app.core.config import settings
from app.core.enums import Role
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Response
from app.schemas.user import (
    ActiveUpdate,
    PasswordChange,
    PasswordReset,
    SignatureUpdate,
    UsernameChange,
    UserBrief,
    UserCreate,
    UserOut,
    UserUpdate,
)

router = APIRouter()


# --------------------------------------------------------------------------- #
# 本人操作（任意登录用户）
# --------------------------------------------------------------------------- #
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


@router.put("/me/password", response_model=Response[dict], summary="修改本人密码")
def change_my_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="原密码错误")
    if payload.new_password == payload.old_password:
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return Response.ok({"id": current_user.id}, message="密码修改成功")


@router.put(
    "/me/username",
    response_model=Response[UserOut],
    summary="修改本人登录账号(用户名)",
)
def change_my_username(
    payload: UsernameChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """本人自助修改登录账号：需当前密码确认；账号唯一。

    令牌以用户 ID 为主体，改名后无需重新登录。
    """
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="密码错误，无法修改登录账号")
    new_name = payload.new_username.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="登录账号不能为空")
    if new_name == current_user.username:
        raise HTTPException(status_code=400, detail="新登录账号与当前一致")
    exists = db.scalar(
        select(User).where(User.username == new_name, User.id != current_user.id)
    )
    if exists:
        raise HTTPException(status_code=400, detail="该登录账号已被占用")
    current_user.username = new_name
    db.commit()
    db.refresh(current_user)
    return Response.ok(UserOut.model_validate(current_user), message="登录账号已更新")


# --------------------------------------------------------------------------- #
# 用户列表（负责人 / 超管可查看）
# --------------------------------------------------------------------------- #
@router.get("", response_model=Response[list[UserBrief]], summary="用户列表 / 组织架构")
def list_users(
    keyword: str | None = None,
    role: Role | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按审批链角色排序展示人员，支持关键字（账号/姓名/部门）、角色、状态筛选。"""
    stmt = select(User)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(User.username.like(like), User.full_name.like(like), User.department.like(like))
        )
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    rows = db.scalars(stmt.order_by(User.id.asc())).all()
    return Response.ok([UserBrief.model_validate(u) for u in rows])


# --------------------------------------------------------------------------- #
# 用户增删改（超级管理员）
# --------------------------------------------------------------------------- #
@router.post("", response_model=Response[UserOut], summary="创建用户(超管)")
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_superuser),
):
    uname = payload.username.strip()
    if not uname:
        raise HTTPException(status_code=400, detail="登录账号不能为空")
    if db.scalar(select(User).where(User.username == uname)):
        raise HTTPException(status_code=400, detail="登录账号已存在")
    user = User(
        username=uname,
        full_name=payload.full_name,
        role=payload.role,
        department=payload.department,
        is_superuser=payload.is_superuser,
        is_active=True,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return Response.ok(UserOut.model_validate(user), message="用户创建成功")


@router.put("/{uid}", response_model=Response[UserOut], summary="编辑用户(超管)")
def update_user(
    uid: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    data = payload.model_dump(exclude_unset=True)
    # 保护：不能取消自己的超管身份 / 停用自己，避免自锁
    if user.id == current_user.id:
        if data.get("is_superuser") is False:
            raise HTTPException(status_code=400, detail="不能取消自己的超级管理员身份")
        if data.get("is_active") is False:
            raise HTTPException(status_code=400, detail="不能停用当前登录账号")
    # 保护：不能撤下最后一个超管
    if data.get("is_superuser") is False and user.is_superuser:
        if _superuser_count(db) <= 1:
            raise HTTPException(status_code=400, detail="必须至少保留一个超级管理员")
    for field, value in data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return Response.ok(UserOut.model_validate(user), message="用户已更新")


@router.put("/{uid}/active", response_model=Response[UserOut], summary="启用/停用用户(超管)")
def set_user_active(
    uid: int,
    payload: ActiveUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="不能停用当前登录账号")
    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return Response.ok(UserOut.model_validate(user), message="状态已更新")


@router.post("/{uid}/reset-password", response_model=Response[dict], summary="重置用户密码(超管)")
def reset_user_password(
    uid: int,
    payload: PasswordReset | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_superuser),
):
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    new_pwd = (payload.new_password if payload else None) or settings.DEFAULT_PASSWORD
    user.hashed_password = hash_password(new_pwd)
    db.commit()
    return Response.ok(
        {"id": uid, "default": not (payload and payload.new_password)},
        message=f"密码已重置为：{new_pwd}",
    )


@router.delete("/{uid}", response_model=Response[dict], summary="删除用户(超管)")
def delete_user(
    uid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    if user.is_superuser and _superuser_count(db) <= 1:
        raise HTTPException(status_code=400, detail="必须至少保留一个超级管理员")
    db.delete(user)
    db.commit()
    return Response.ok({"id": uid}, message="用户已删除")


def _superuser_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.is_superuser.is_(True))) or 0
