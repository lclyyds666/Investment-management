from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_superuser
from app.core.enums import (
    AssignmentStatus,
    WorkflowAction,
    WorkflowAssigneeMode,
    WorkflowTargetType,
    WorkflowTaskStatus,
)
from app.db.session import get_db
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.organization import ExternalAssignment, Organization, Position, UserAssignment
from app.models.user import User
from app.models.workflow import WorkflowInstance, WorkflowTask, WorkflowTaskAction
from app.schemas.common import Response
from app.schemas.workflow import WorkflowSubmissionPlan, WorkflowTimelineTask
from app.services.assignment_permissions import (
    PermissionContext,
    active_assignments,
    has_permission,
)
from app.services.contract_workflow import (
    CONTRACT_WORKFLOW_CODES,
    contract_node_candidates,
    submission_plan,
)
from app.services.legal_record_scope import can_access_contract, legal_record_scope
from app.services.workflow_engine import (
    WorkflowTaskConflict,
    WorkflowValidationError,
    complete_task,
    eligible_designated_users,
    eligible_users_for_position,
    my_active_tasks,
    project_contract_action,
    refresh_invalid_designated_tasks,
)


router = APIRouter()


class WorkflowApproveRequest(BaseModel):
    comment: str = ""


class WorkflowRejectRequest(BaseModel):
    reason: str


class WorkflowReassignRequest(BaseModel):
    user_id: int
    reason: str


SUBMIT_PERMISSION_BY_WORKFLOW = {
    "supply.contract.v2": "supply.contract.submit",
    "supply.payment.v2": "supply.approval.submit",
    "supply.business.v2": "supply.approval.submit",
    "investment.contract.department.v1": "investment.legal.contracts.submit",
    "investment.contract.subsidiary.v1": "investment.legal.contracts.submit",
    "investment.contract.legal-risk.v1": "investment.legal.contracts.submit",
}


def _workflow_error(error: WorkflowValidationError) -> HTTPException:
    if error.code in {"workflow_task_not_found", "workflow_target_not_found"}:
        http_status = status.HTTP_404_NOT_FOUND
    elif error.code == "workflow_task_not_actionable":
        http_status = status.HTTP_403_FORBIDDEN
    else:
        http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(
        status_code=http_status,
        detail={"code": error.code, "message": error.message, **error.details},
    )


def _required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must not be blank",
        )
    return normalized


def _target_title(db: Session, target_type: WorkflowTargetType, target_id: int) -> str:
    if target_type == WorkflowTargetType.CONTRACT:
        target = db.get(Contract, target_id)
        return target.title if target is not None else ""
    target = db.get(ApprovalForm, target_id)
    if target is None:
        return ""
    return target.business_desc or target.contract_no or f"审批单 #{target.id}"


def _task_card(db: Session, task: WorkflowTask) -> dict:
    return {
        "id": task.id,
        "instance_id": task.instance_id,
        "target_type": task.instance.target_type,
        "target_id": task.instance.target_id,
        "target_title": _target_title(db, task.instance.target_type, task.instance.target_id),
        "node_code": task.node.code,
        "node_name": task.node.name,
        "mode": task.assignee_mode,
        "designated_user": (
            {"id": task.designated_user.id, "full_name": task.designated_user.full_name}
            if task.designated_user is not None else None
        ),
        "activated_at": task.activated_at,
        "allowed_actions": [
            WorkflowAction.APPROVE.value,
            *([WorkflowAction.RETURN.value] if task.node.allow_reject else []),
        ],
    }


def _load_instance(db: Session, instance_id: int) -> WorkflowInstance:
    instance = db.scalar(
        select(WorkflowInstance)
        .where(WorkflowInstance.id == instance_id)
        .options(
            joinedload(WorkflowInstance.tasks)
            .joinedload(WorkflowTask.actions),
            joinedload(WorkflowInstance.tasks).joinedload(WorkflowTask.node),
            joinedload(WorkflowInstance.tasks).joinedload(WorkflowTask.designated_user),
        )
    )
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow instance not found")
    return instance


def _contract_submission_target(
    db: Session,
    target_type: WorkflowTargetType,
    target_id: int,
    current_user: User,
) -> Contract:
    if target_type != WorkflowTargetType.CONTRACT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="submission plan currently supports contracts only",
        )
    contract = db.get(Contract, target_id)
    if contract is None or not can_access_contract(
        db, contract, legal_record_scope(db, current_user)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="合同不存在"
        )
    if contract.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能提交本人创建的合同")
    permission_contexts = [
        PermissionContext(company_code="investment"),
        PermissionContext(
            company_code=contract.company_code,
            department_code=contract.organization_code,
        ),
        *(
            PermissionContext(
                company_code=assignment.organization.company_code,
                department_code=(
                    assignment.organization.code
                    if assignment.organization.organization_type.value == "department"
                    else None
                ),
            )
            for assignment in active_assignments(db, current_user.id)
        ),
    ]
    permission_code = (
        "supply.contract.submit"
        if contract.workflow_route_version < 1
        else "investment.legal.contracts.submit"
    )
    if not any(
        has_permission(
            db,
            current_user,
            permission_code,
            context,
        )
        for context in permission_contexts
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return contract


@router.get("/submission-plan", response_model=Response[WorkflowSubmissionPlan])
def workflow_submission_plan(
    target_type: WorkflowTargetType = Query(...),
    target_id: int = Query(..., ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contract = _contract_submission_target(
        db, target_type, target_id, current_user
    )
    try:
        plan = submission_plan(db, contract, current_user)
    except WorkflowValidationError as error:
        raise _workflow_error(error) from error
    return Response.ok(plan)


@router.get("/candidates", response_model=Response[list[dict]])
def candidates(
    workflow_code: str | None = Query(None, min_length=1),
    node_code: str | None = Query(None, min_length=1),
    task_id: int | None = Query(None, ge=1),
    target_type: WorkflowTargetType | None = Query(None),
    target_id: int | None = Query(None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task_selector = task_id is not None
    catalog_selector = workflow_code is not None or node_code is not None
    if task_selector == catalog_selector or (catalog_selector and not (workflow_code and node_code)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="provide exactly task_id or workflow_code with node_code",
        )
    if (target_type is None) != (target_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="target_type and target_id must be provided together",
        )
    if task_id is not None:
        if not current_user.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        task = db.scalar(
            select(WorkflowTask)
            .where(WorkflowTask.id == task_id)
            .options(
                joinedload(WorkflowTask.instance).joinedload(WorkflowInstance.definition),
                joinedload(WorkflowTask.node),
            )
        )
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow task not found")
        if task.assignee_mode != WorkflowAssigneeMode.DESIGNATED_USER:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="only designated tasks have reassignment candidates")
        if task.status != WorkflowTaskStatus.AWAITING_REASSIGNMENT:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="task is not awaiting reassignment")
        result = eligible_users_for_position(
            db,
            task.required_position_code,
            date.today(),
            exclude_user_id=task.designated_user_id,
        )
    if task_id is not None:
        participant_ids = set(db.scalars(
            select(WorkflowTask.designated_user_id).where(
                WorkflowTask.instance_id == task.instance_id,
                WorkflowTask.id != task.id,
                WorkflowTask.designated_user_id.is_not(None),
            )
        ).all())
        participant_ids.update(db.scalars(
            select(WorkflowTaskAction.actor_id)
            .join(WorkflowTask, WorkflowTaskAction.task_id == WorkflowTask.id)
            .where(WorkflowTask.instance_id == task.instance_id, WorkflowTask.id != task.id)
        ).all())
        participant_ids.add(task.instance.submitted_by)
        return Response.ok([
            item.model_dump() for item in result if item.user_id not in participant_ids
        ])
    permission_code = SUBMIT_PERMISSION_BY_WORKFLOW.get(workflow_code)
    if permission_code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")
    permission_context = PermissionContext(
        company_code=(
            "investment"
            if workflow_code in CONTRACT_WORKFLOW_CODES
            else "supplymanagement"
        )
    )
    if (
        task_id is None
        and workflow_code not in CONTRACT_WORKFLOW_CODES
        and not has_permission(
            db,
            current_user,
            permission_code,
            permission_context,
        )
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        if workflow_code in CONTRACT_WORKFLOW_CODES:
            if target_type is None or target_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="contract candidates require target_type and target_id",
                )
            contract = _contract_submission_target(
                db, target_type, target_id, current_user
            )
            result = contract_node_candidates(
                db,
                contract,
                current_user,
                workflow_code,
                node_code,
                date.today(),
                exclude_user_id=current_user.id,
            )
        elif (
            workflow_code == "supply.contract.v2"
            and target_type is not None
            and target_id is not None
        ):
            contract = _contract_submission_target(
                db, target_type, target_id, current_user
            )
            if contract.workflow_route_version >= 1:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="new contracts require an ownership-routed workflow",
                )
            result = eligible_designated_users(
                db,
                workflow_code,
                node_code,
                date.today(),
                exclude_user_id=current_user.id,
            )
        else:
            if target_type is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="legacy workflow candidates do not accept a target",
                )
            result = eligible_designated_users(
                db,
                workflow_code,
                node_code,
                date.today(),
                exclude_user_id=current_user.id,
            )
    except WorkflowValidationError as error:
        raise _workflow_error(error) from error
    return Response.ok([item.model_dump() for item in result])


def _invalidation_reason(task: WorkflowTask) -> str:
    assignment = task.designated_assignment
    if task.designated_user is None or not task.designated_user.is_active:
        return "原办理人账号已停用"
    if assignment is None:
        return "原办理人的岗位任职已移除"
    if assignment.status != AssignmentStatus.ACTIVE:
        return "原办理人的岗位任职已停用"
    if assignment.valid_until is not None and assignment.valid_until < date.today():
        return "原办理人的岗位任职已过期"
    return "原办理人的岗位任职已失效"


@router.get("/awaiting-reassignment", response_model=Response[list[dict]])
def awaiting_reassignment(
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
):
    refresh_invalid_designated_tasks(db)
    db.commit()
    tasks = db.scalars(
        select(WorkflowTask)
        .where(WorkflowTask.status == WorkflowTaskStatus.AWAITING_REASSIGNMENT)
        .options(
            joinedload(WorkflowTask.instance),
            joinedload(WorkflowTask.node),
            joinedload(WorkflowTask.designated_user),
            joinedload(WorkflowTask.designated_assignment),
        )
        .order_by(WorkflowTask.activated_at, WorkflowTask.id)
    ).all()
    return Response.ok([{
        "id": task.id,
        "instance_id": task.instance_id,
        "target_type": task.instance.target_type,
        "target_id": task.instance.target_id,
        "target_title": _target_title(db, task.instance.target_type, task.instance.target_id),
        "node_code": task.node.code,
        "node_name": task.node.name,
        "previous_assignee": (
            {"id": task.designated_user.id, "full_name": task.designated_user.full_name}
            if task.designated_user is not None else None
        ),
        "invalidation_reason": _invalidation_reason(task),
        "activated_at": task.activated_at,
        "required_position_code": task.required_position_code,
        "required_position_name": task.required_position_name or task.required_position_code,
    } for task in tasks])


@router.get("/reassignment-audits", response_model=Response[dict])
def reassignment_audits(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
):
    filters = (WorkflowTaskAction.action == WorkflowAction.REASSIGN,)
    total = db.scalar(select(func.count(WorkflowTaskAction.id)).where(*filters)) or 0
    actions = db.scalars(
        select(WorkflowTaskAction)
        .where(*filters)
        .options(joinedload(WorkflowTaskAction.task))
        .order_by(WorkflowTaskAction.created_at.desc(), WorkflowTaskAction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Response.ok({"items": [{
        "id": action.id,
        "task_id": action.task_id,
        "old_assignee_name": action.previous_assignee_name,
        "new_assignee_name": action.new_assignee_name,
        "required_position_code": action.task.required_position_code,
        "required_position_name": action.task.required_position_name or action.task.required_position_code,
        "operator_name": action.actor_name,
        "reason": action.reason or action.comment,
        "created_at": action.created_at,
    } for action in actions], "total": total, "page": page, "page_size": page_size})


@router.get("/my-tasks", response_model=Response[list[dict]])
def inbox(
    target_type: WorkflowTargetType | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tasks = my_active_tasks(db, current_user, target_type)
    for task in tasks:
        if task.designated_user_id is not None:
            task.designated_user
    return Response.ok([_task_card(db, task) for task in tasks])


@router.get(
    "/instances/{instance_id}/timeline",
    response_model=Response[list[WorkflowTimelineTask]],
)
def timeline(
    instance_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instance = _load_instance(db, instance_id)
    view_permission = (
        "supply.contract.view"
        if instance.target_type == WorkflowTargetType.CONTRACT
        else "supply.approval.view"
    )
    is_designated_for_instance = bool(db.scalar(select(exists().where(
        WorkflowTask.instance_id == instance.id,
        WorkflowTask.designated_user_id == current_user.id,
    ))))
    if not current_user.is_superuser and not has_permission(
        db,
        current_user,
        view_permission,
        PermissionContext(
            company_code="supplymanagement",
            assigned_user_id=current_user.id if is_designated_for_instance else None,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    tasks = sorted(instance.tasks, key=lambda item: (item.sequence, item.id))
    return Response.ok([
        {
            "id": task.id,
            "sequence": task.sequence,
            "node_code": task.node.code,
            "node_name": task.node.name,
            "mode": task.assignee_mode,
            "required_position_code": task.required_position_code,
            "required_position_name": task.required_position_name or task.required_position_code,
            "designated_user": (
                {"id": task.designated_user.id, "full_name": task.designated_user.full_name}
                if task.designated_user is not None else None
            ),
            "status": task.status,
            "activated_at": task.activated_at,
            "completed_at": task.completed_at,
            "actions": [
                {
                    "id": action.id,
                    "task_id": action.task_id,
                    "node_code": task.node.code,
                    "node_name": task.node.name,
                    "action": action.action,
                    "actor_id": action.actor_id,
                    "actor_name": action.actor_name,
                    "organization_code": action.organization_code,
                    "organization_name": action.organization_name,
                    "position_code": action.position_code,
                    "position_name": action.position_name,
                    "comment": action.comment,
                    "previous_assignee_id": action.previous_assignee_id,
                    "previous_assignee_name": action.previous_assignee_name,
                    "new_assignee_id": action.new_assignee_id,
                    "new_assignee_name": action.new_assignee_name,
                    "reason": action.reason,
                    "returned_to_sequence": action.returned_to_sequence,
                    "created_at": action.created_at,
                }
                for action in sorted(task.actions, key=lambda item: (item.created_at, item.id))
            ],
        }
        for task in tasks
    ])


def _complete(
    db: Session,
    task_id: int,
    current_user: User,
    action: WorkflowAction,
    comment: str,
):
    try:
        instance = complete_task(db, task_id, current_user, action, comment)
        db.commit()
    except WorkflowTaskConflict as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": error.code,
                "actor": error.actor_name,
                "action": error.action,
                "completed_at": error.completed_at.isoformat(),
            },
        ) from error
    except WorkflowValidationError as error:
        db.rollback()
        raise _workflow_error(error) from error
    return Response.ok({"instance_id": instance.id, "status": instance.status})


@router.post("/tasks/{task_id}/approve", response_model=Response[dict])
def approve(
    task_id: int,
    payload: WorkflowApproveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _complete(db, task_id, current_user, WorkflowAction.APPROVE, payload.comment.strip())


@router.post("/tasks/{task_id}/reject", response_model=Response[dict])
def reject(
    task_id: int,
    payload: WorkflowRejectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _complete(
        db,
        task_id,
        current_user,
        WorkflowAction.RETURN,
        _required_text(payload.reason, "reason"),
    )


def _effective_exact_assignment(db: Session, user_id: int, position_code: str) -> UserAssignment | None:
    today = date.today()
    assignment = db.scalar(
        select(UserAssignment)
        .join(UserAssignment.user)
        .join(UserAssignment.organization)
        .join(UserAssignment.position)
        .where(
            UserAssignment.user_id == user_id,
            UserAssignment.status == AssignmentStatus.ACTIVE,
            UserAssignment.valid_from <= today,
            or_(UserAssignment.valid_until.is_(None), UserAssignment.valid_until >= today),
            User.is_active.is_(True),
            Organization.is_active.is_(True),
            Position.is_active.is_(True),
            Position.code == position_code,
        )
        .options(
            joinedload(UserAssignment.user),
            joinedload(UserAssignment.organization),
            joinedload(UserAssignment.position),
            joinedload(UserAssignment.external_detail),
        )
        .order_by(UserAssignment.id)
    )
    if (
        assignment is not None
        and position_code == "external.legal_counsel"
        and (
            assignment.external_detail is None
            or "contract_legal_review" not in assignment.external_detail.service_scopes
        )
    ):
        return None
    return assignment


@router.post("/tasks/{task_id}/reassign", response_model=Response[dict])
def reassign(
    task_id: int,
    payload: WorkflowReassignRequest,
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
):
    reason = _required_text(payload.reason, "reason")
    task = db.scalar(
        select(WorkflowTask)
        .where(WorkflowTask.id == task_id)
        .options(joinedload(WorkflowTask.designated_user))
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow task not found")
    if task.assignee_mode != WorkflowAssigneeMode.DESIGNATED_USER:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="only designated tasks can be reassigned")
    if task.status != WorkflowTaskStatus.AWAITING_REASSIGNMENT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="task cannot be reassigned in its current status")
    if payload.user_id == task.designated_user_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="the invalid previous assignee cannot be selected again")
    assignment = _effective_exact_assignment(db, payload.user_id, task.required_position_code)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="new assignee lacks an effective exact-position assignment")
    duplicate_actor = db.scalar(select(exists().where(
        WorkflowTask.instance_id == task.instance_id,
        WorkflowTask.id != task.id,
        or_(
            WorkflowTask.designated_user_id == payload.user_id,
            exists().where(
                WorkflowTaskAction.task_id == WorkflowTask.id,
                WorkflowTaskAction.actor_id == payload.user_id,
            ),
        ),
    )))
    if payload.user_id == task.instance.submitted_by or duplicate_actor:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="user already participates in this workflow instance")

    previous_assignee = task.designated_user
    updated = db.execute(
        update(WorkflowTask)
        .where(
            WorkflowTask.id == task.id,
            WorkflowTask.status == task.status,
            WorkflowTask.version == task.version,
        )
        .values(
            designated_user_id=assignment.user_id,
            designated_assignment_id=assignment.id,
            status=WorkflowTaskStatus.ACTIVE,
            version=WorkflowTask.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if updated.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "workflow_task_reassignment_conflict", "message": "The task changed before reassignment."},
        )
    reassignment_action = WorkflowTaskAction(
        task_id=task.id,
        action=WorkflowAction.REASSIGN,
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        organization_code="system",
        organization_name="系统管理",
        position_code="system.information_maintainer",
        position_name="信息维护者",
        comment=reason,
        signature_snapshot=current_user.signature,
        previous_assignee_id=previous_assignee.id if previous_assignee is not None else None,
        previous_assignee_name=(previous_assignee.full_name if previous_assignee is not None else None),
        new_assignee_id=assignment.user_id,
        new_assignee_name=assignment.user.full_name,
        reason=reason,
    )
    db.add(reassignment_action)
    db.flush()
    project_contract_action(db, task.instance, task, reassignment_action)
    db.commit()
    db.refresh(task)
    return Response.ok({
        "task_id": task.id,
        "previous_assignee": (
            {"id": previous_assignee.id, "full_name": previous_assignee.full_name}
            if previous_assignee is not None else None
        ),
        "new_assignee": {"id": assignment.user.id, "full_name": assignment.user.full_name},
        "status": task.status,
    })
