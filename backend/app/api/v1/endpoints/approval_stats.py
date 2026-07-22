"""审批角标统计端点 —— 按当前登录用户角色统计「待我处理」的审批数量。

供前端侧边栏在「合同管理」「业务审批」及其分组上渲染 Badge 角标。
两条独立审批流各自统计（互不干扰）：
- contract：合同(法律)类审批，链见 enums.APPROVAL_CHAIN；
- business：业务审批单(付款/业务两套链)，链见 enums.form_role_at_step。

判定「待我审批」：审批单处于 pending 且当前流转环节角色 == 我的角色；
超级管理员可审批任意环节，故统计其为「全部 pending」。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.enums import ContractStatus, form_role_at_step, role_at_step
from app.db.session import get_db
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.user import User
from app.schemas.common import Response

router = APIRouter()


@router.get("/pending-count", response_model=Response[dict], summary="待我审批数量(合同/业务审批,供导航角标)")
def pending_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_super = current_user.is_superuser
    my_role = current_user.role

    # 合同(法律)类审批
    contracts = db.scalars(
        select(Contract).where(Contract.status == ContractStatus.PENDING)
    ).all()
    contract_cnt = sum(
        1 for c in contracts
        if is_super or role_at_step(c.current_step) == my_role
    )

    # 业务审批单（付款单 7 节点 / 业务单 5 节点，按 form_type 分派）
    forms = db.scalars(
        select(ApprovalForm).where(ApprovalForm.status == ContractStatus.PENDING)
    ).all()
    business_cnt = sum(
        1 for f in forms
        if is_super or form_role_at_step(f.form_type, f.current_step) == my_role
    )

    return Response.ok({
        "contract": contract_cnt,
        "business": business_cnt,
        "total": contract_cnt + business_cnt,
    })
