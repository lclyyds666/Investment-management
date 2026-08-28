"""Fund transaction ledger endpoints."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.enums import CompanyCode
from app.db.session import get_db
from app.models.fund import FundTransaction
from app.models.user import User
from app.schemas.common import Response
from app.schemas.fund import (
    DUE_CATEGORIES,
    FundSettleIn,
    FundSummary,
    FundTransactionCreate,
    FundTransactionOut,
    FundTransactionUpdate,
)
from app.services.assignment_permissions import PermissionContext
from app.services.fund import maturity_state, summarize_funds


router = APIRouter()

_supply_context = lambda: PermissionContext(
    company_code=CompanyCode.SUPPLY_MANAGEMENT.value
)
_view_guard = require_permission("supply.finance.view", _supply_context)
_update_guard = require_permission("supply.finance.update", _supply_context)


def _out(row: FundTransaction, today: date | None = None) -> FundTransactionOut:
    output = FundTransactionOut.model_validate(row)
    return output.model_copy(update={"maturity_status": maturity_state(row, today or date.today())})


@router.get("", response_model=Response[dict], summary="资金流水台账")
def list_funds(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    direction: str | None = None,
    category: str | None = None,
    settlement_status: str | None = None,
    maturity_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    statement = select(FundTransaction)
    if direction:
        statement = statement.where(FundTransaction.direction == direction)
    if category:
        statement = statement.where(FundTransaction.category == category)
    if settlement_status:
        statement = statement.where(FundTransaction.settlement_status == settlement_status)
    if start_date:
        statement = statement.where(FundTransaction.occurred_on >= start_date)
    if end_date:
        statement = statement.where(FundTransaction.occurred_on <= end_date)
    if keyword and keyword.strip():
        phrase = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(
                FundTransaction.counterparty.ilike(phrase),
                FundTransaction.summary.ilike(phrase),
                FundTransaction.remark.ilike(phrase),
            )
        )

    rows = db.scalars(
        statement.order_by(FundTransaction.occurred_on.desc(), FundTransaction.id.desc())
    ).all()
    today = date.today()
    if maturity_status:
        rows = [row for row in rows if maturity_state(row, today) == maturity_status]
    total = len(rows)
    start = (page - 1) * page_size
    items = [_out(row, today) for row in rows[start:start + page_size]]
    return Response.ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/summary", response_model=Response[FundSummary], summary="资金汇总与到期预警")
def fund_summary(
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    rows = db.scalars(select(FundTransaction)).all()
    return Response.ok(summarize_funds(rows, date.today()))


@router.post("", response_model=Response[FundTransactionOut], summary="新增资金流水")
def create_fund(
    payload: FundTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_update_guard),
):
    row = FundTransaction(
        **payload.model_dump(),
        settlement_status="open",
        settled_on=None,
        created_by=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return Response.ok(_out(row), message="资金流水已新增")


@router.put("/{fund_id}", response_model=Response[FundTransactionOut], summary="编辑资金流水")
def update_fund(
    fund_id: int,
    payload: FundTransactionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(_update_guard),
):
    row = db.get(FundTransaction, fund_id)
    if not row:
        raise HTTPException(status_code=404, detail="资金流水不存在")
    if row.settlement_status == "settled" and (
        payload.direction != row.direction or payload.category != row.category
    ):
        raise HTTPException(status_code=409, detail="已结清资金流水不能修改资金方向或类型")
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return Response.ok(_out(row), message="资金流水已更新")


@router.delete("/{fund_id}", response_model=Response[dict], summary="删除资金流水")
def delete_fund(
    fund_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_update_guard),
):
    row = db.get(FundTransaction, fund_id)
    if not row:
        raise HTTPException(status_code=404, detail="资金流水不存在")
    db.delete(row)
    db.commit()
    return Response.ok({"id": fund_id}, message="资金流水已删除")


@router.post("/{fund_id}/settle", response_model=Response[FundTransactionOut], summary="结清授信或借款")
def settle_fund(
    fund_id: int,
    payload: FundSettleIn,
    db: Session = Depends(get_db),
    _: User = Depends(_update_guard),
):
    row = db.get(FundTransaction, fund_id)
    if not row:
        raise HTTPException(status_code=404, detail="资金流水不存在")
    if row.category not in DUE_CATEGORIES:
        raise HTTPException(status_code=400, detail="只有银行授信和公司借款可以结清")
    settled_on = payload.settled_on or date.today()
    if settled_on < row.occurred_on:
        raise HTTPException(status_code=400, detail="结清日期不能早于发生日期")
    row.settlement_status = "settled"
    row.settled_on = settled_on
    db.commit()
    db.refresh(row)
    return Response.ok(_out(row), message="资金已结清")
