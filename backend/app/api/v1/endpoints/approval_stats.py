"""审批角标统计端点 —— 按当前登录用户角色统计「待我处理」的审批数量。

供前端侧边栏在「合同管理」「业务审批」及其分组上渲染 Badge 角标。
两条独立审批流各自统计（互不干扰）：
- contract：合同(法律)类审批，链见 enums.APPROVAL_CHAIN；
- business：业务审批单(付款/业务两套链)，链见 enums.form_role_at_step。

判定「待我审批」：用户具备对应模块查看权限，审批单处于 pending，且当前流转环节角色
匹配用户的有效岗位。超级管理员没有业务岗位兜底。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.enums import CompanyCode, ContractStatus, Role, form_role_at_step, role_at_step
from app.db.session import get_db
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.user import User
from app.schemas.common import Response
from app.services.assignment_permissions import PermissionContext, has_permission, has_position

router = APIRouter()

_supply_context = lambda: PermissionContext(company_code=CompanyCode.SUPPLY_MANAGEMENT.value)

_ROLE_POSITIONS = {
    Role.BUSINESS_HANDLER: "supply.business_handler",
    Role.BUSINESS_REVIEWER: "supply.business_reviewer",
    Role.FINANCE_HANDLER: "supply.finance_handler",
    Role.SCM_DIRECTOR: "supply.company_leader",
    Role.RISK_AUDITOR: "investment.duty.supply_risk_review",
    Role.FINANCE_REVIEWER: "investment.duty.supply_finance_review",
    Role.INVEST_DIRECTOR: "governance.supply_leader",
    Role.LEGAL_COUNSEL: "external.legal_counsel",
}


def _require_pending_view(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    context = _supply_context()
    if not any(
        has_permission(db, current_user, permission_code, context)
        for permission_code in ("supply.contract.view", "supply.approval.view")
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return current_user


@router.get(
    "/pending-count",
    response_model=Response[dict],
    summary="待我审批数量(合同/业务审批,供导航角标)",
)
def pending_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_pending_view),
):
    my_role = next(
        (role for role, code in _ROLE_POSITIONS.items() if has_position(db, current_user.id, code)),
        None,
    )

    # 合同(法律)类审批
    context = _supply_context()
    contract_cnt = 0
    if has_permission(db, current_user, "supply.contract.view", context):
        contracts = db.scalars(
            select(Contract).where(Contract.status == ContractStatus.PENDING)
        ).all()
        contract_cnt = sum(
            1 for contract in contracts
            if role_at_step(contract.current_step) == my_role
        )

    # 业务审批单（付款单 7 节点 / 业务单 5 节点，按 form_type 分派）
    business_cnt = 0
    if has_permission(db, current_user, "supply.approval.view", context):
        forms = db.scalars(
            select(ApprovalForm).where(ApprovalForm.status == ContractStatus.PENDING)
        ).all()
        business_cnt = sum(
            1 for form in forms
            if form_role_at_step(form.form_type, form.current_step) == my_role
        )

    return Response.ok({
        "contract": contract_cnt,
        "business": business_cnt,
        "total": contract_cnt + business_cnt,
    })
