"""审批角标统计端点，按可执行工作流任务计数。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.enums import CompanyCode, WorkflowTargetType
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Response
from app.services.assignment_permissions import permission_grants
from app.services.workflow_engine import (
    actionable_active_task_counts,
    awaiting_reassignment_count,
)

router = APIRouter()

_VIEW_PERMISSIONS = {"supply.contract.view", "supply.approval.view"}

def _require_pending_view(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if current_user.is_superuser:
        return current_user
    if not _VIEW_PERMISSIONS.intersection(
        grant.code for grant in permission_grants(db, current_user.id)
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
    grant_codes = (
        set()
        if current_user.is_superuser
        else {grant.code for grant in permission_grants(db, current_user.id)}
    )
    counts = (
        {}
        if current_user.is_superuser
        else actionable_active_task_counts(db, current_user)
    )
    contract_cnt = (
        counts.get(WorkflowTargetType.CONTRACT, 0)
        if "supply.contract.view" in grant_codes
        else 0
    )
    business_cnt = (
        counts.get(WorkflowTargetType.PAYMENT_APPROVAL, 0)
        + counts.get(WorkflowTargetType.BUSINESS_APPROVAL, 0)
        if "supply.approval.view" in grant_codes
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
