"""客户档案管理端点（主数据 CRUD）。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.enums import Role
from app.core.masking import mask_phone
from app.db.session import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.common import Response
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate

router = APIRouter()

# 可维护客户档案的角色
WRITE_ROLES = (Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR)


def _dump_files(payload_dict: dict) -> dict:
    # admission_files 为 pydantic 模型列表，转为可入 JSON 的 dict 列表
    if payload_dict.get("admission_files") is not None:
        payload_dict["admission_files"] = [
            f if isinstance(f, dict) else f.model_dump() for f in payload_dict["admission_files"]
        ]
    return payload_dict


@router.get("", response_model=Response[list[CustomerOut]], summary="客户列表")
def list_customers(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """列表默认对联系电话脱敏（138****5678），明文仅在详情页按需返回。"""
    rows = db.scalars(select(Customer).order_by(Customer.id.desc())).all()
    out = []
    for r in rows:
        item = CustomerOut.model_validate(r)
        item.phone = mask_phone(item.phone)
        out.append(item)
    return Response.ok(out)


@router.get("/{cid}", response_model=Response[CustomerOut], summary="客户详情")
def get_customer(cid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    return Response.ok(CustomerOut.model_validate(c))


@router.post(
    "", response_model=Response[CustomerOut], summary="新建客户",
    dependencies=[Depends(require_roles(*WRITE_ROLES))],
)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Customer).where(Customer.customer_code == payload.customer_code)):
        raise HTTPException(status_code=400, detail="客户ID已存在")
    c = Customer(**_dump_files(payload.model_dump()))
    db.add(c)
    db.commit()
    db.refresh(c)
    return Response.ok(CustomerOut.model_validate(c))


@router.put(
    "/{cid}", response_model=Response[CustomerOut], summary="修改客户",
    dependencies=[Depends(require_roles(*WRITE_ROLES))],
)
def update_customer(cid: int, payload: CustomerUpdate, db: Session = Depends(get_db)):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    for field, value in _dump_files(payload.model_dump(exclude_unset=True)).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return Response.ok(CustomerOut.model_validate(c))


@router.delete(
    "/{cid}", response_model=Response[dict], summary="删除客户",
    dependencies=[Depends(require_roles(*WRITE_ROLES))],
)
def delete_customer(cid: int, db: Session = Depends(get_db)):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    db.delete(c)
    db.commit()
    return Response.ok({"id": cid})
