"""审批角标统计端点，按可执行工作流任务计数。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.enums import CompanyCode, WorkflowTargetType
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Response
from app.services.assignment_permissions import PermissionContext, has_permission
from app.services.workflow_engine import (
    actionable_active_task_counts,
    awaiting_reassignment_count,
)

router = APIRouter()

_supply_context = lambda: PermissionContext(company_code=CompanyCode.SUPPLY_MANAGEMENT.value)

def _require_pending_view(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if current_user.is_superuser:
        return current_user
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
    context = _supply_context()
    counts = {} if current_user.is_superuser else actionable_active_task_counts(db, current_user)
    contract_cnt = (
        counts.get(WorkflowTargetType.CONTRACT, 0)
        if has_permission(db, current_user, "supply.contract.view", context)
        else 0
    )
    business_cnt = (
        counts.get(WorkflowTargetType.PAYMENT_APPROVAL, 0)
        + counts.get(WorkflowTargetType.BUSINESS_APPROVAL, 0)
        if has_permission(db, current_user, "supply.approval.view", context)
        else 0
    )
    result = {
        "contract": contract_cnt,
        "business": business_cnt,
        "total": contract_cnt + business_cnt,
    }
    if current_user.is_superuser:
        result["reassignment"] = awaiting_reassignment_count(db)
    return Response.ok(result)
