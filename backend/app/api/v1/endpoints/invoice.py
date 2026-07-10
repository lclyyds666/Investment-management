"""发票管理端点（财务模块扩展）。"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.enums import DIRECTOR_ROLES, FINANCE_ROLES, InvoiceStatus
from app.db.session import get_db
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.common import Response
from app.schemas.invoice import InvoiceCreate, InvoiceOut, InvoiceStats, InvoiceUpdate

router = APIRouter()

WRITE_ROLES = (*FINANCE_ROLES, *DIRECTOR_ROLES)


@router.get("", response_model=Response[list[InvoiceOut]], summary="发票列表")
def list_invoices(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(Invoice).order_by(Invoice.id.desc())).all()
    return Response.ok([InvoiceOut.model_validate(r) for r in rows])


@router.get("/stats", response_model=Response[InvoiceStats], summary="发票开票统计")
def invoice_stats(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(Invoice)).all()
    issued_amt = sum((r.amount for r in rows if r.status == InvoiceStatus.ISSUED), Decimal("0"))
    pending_amt = sum((r.amount for r in rows if r.status == InvoiceStatus.PENDING), Decimal("0"))
    return Response.ok(InvoiceStats(
        total=len(rows),
        pending=sum(1 for r in rows if r.status == InvoiceStatus.PENDING),
        issued=sum(1 for r in rows if r.status == InvoiceStatus.ISSUED),
        void=sum(1 for r in rows if r.status == InvoiceStatus.VOID),
        issued_amount=issued_amt,
        pending_amount=pending_amt,
    ))


@router.post(
    "", response_model=Response[InvoiceOut], summary="新建发票",
    dependencies=[Depends(require_roles(*WRITE_ROLES))],
)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    inv = Invoice(**payload.model_dump())
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return Response.ok(InvoiceOut.model_validate(inv))


@router.put(
    "/{iid}", response_model=Response[InvoiceOut], summary="修改发票/更新开票状态",
    dependencies=[Depends(require_roles(*WRITE_ROLES))],
)
def update_invoice(iid: int, payload: InvoiceUpdate, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv:
        raise HTTPException(status_code=404, detail="发票不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(inv, field, value)
    db.commit()
    db.refresh(inv)
    return Response.ok(InvoiceOut.model_validate(inv))


@router.delete(
    "/{iid}", response_model=Response[dict], summary="删除发票",
    dependencies=[Depends(require_roles(*WRITE_ROLES))],
)
def delete_invoice(iid: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv:
        raise HTTPException(status_code=404, detail="发票不存在")
    db.delete(inv)
    db.commit()
    return Response.ok({"id": iid})
