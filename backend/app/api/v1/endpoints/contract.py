"""合同全生命周期与岗位工作流兼容端点。"""
import csv
import io
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.enums import (
    ContractStatus,
    WorkflowAction,
    WorkflowTargetType,
    WorkflowTaskStatus,
)
from app.db.session import get_db
from app.models.approval import Approval
from app.models.contract import Contract
from app.models.user import User
from app.models.workflow import WorkflowInstance, WorkflowTask
from app.schemas.approval import ApprovalOut, ApproveRequest, RejectRequest
from app.schemas.common import Response
from app.schemas.contract import ContractCreate, ContractOut, ContractUpdate
from app.schemas.workflow import WorkflowStartRequest
from app.services.contract_evidence import deterministic_findings, retrieve_evidence
from app.services.contract_review import render_review_markdown
from app.services.contract_review_llm import review_with_evidence
from app.services import customer_research as research_svc
from app.services import legal_doc as legal_doc_svc
from app.services.contract_workflow import contract_workflow_code
from app.services.assignment_permissions import PermissionContext, active_assignments, has_permission
from app.services.legal_ownership import LegalOwnershipError, resolve_legal_ownership
from app.services.legal_record_scope import (
    can_access_contract,
    contract_access_predicate,
    legal_record_scope,
)
from app.services.workflow_engine import (
    WorkflowTaskConflict,
    WorkflowValidationError,
    cancel_active_workflow_for_target,
    complete_task,
    my_active_tasks,
    start_workflow,
    task_is_actionable_by,
)

_OPINION_POSITIONS = {code for code, _ in legal_doc_svc.OPINION_ROLES}
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter()

def _contract_permission_guard(permission_code: str):
    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not _has_contract_permission(db, current_user, permission_code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return current_user

    return checker


_view_guard = _contract_permission_guard("investment.legal.contracts.view")
_create_guard = _contract_permission_guard("investment.legal.contracts.create")
_update_guard = _contract_permission_guard("investment.legal.contracts.update")
_submit_guard = _contract_permission_guard("investment.legal.contracts.submit")
_export_guard = _contract_permission_guard("investment.legal.contracts.export")

# 合同附件允许的扩展名（与前端 accept 对齐）
_ATTACH_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"}
_ATTACH_MAX_BYTES = 20 * 1024 * 1024  # 单个附件 ≤ 20MB
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _get_contract_or_404(db: Session, contract_id: int) -> Contract:
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="合同不存在")
    return contract


def _names_map(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all()
    return {i: n for i, n in rows}


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_CSV_FORMULA_PREFIXES) else text


def _active_task_for_contract(db: Session, contract: Contract) -> WorkflowTask | None:
    if contract.workflow_instance_id is None:
        return None
    return db.scalar(
        select(WorkflowTask)
        .where(
            WorkflowTask.instance_id == contract.workflow_instance_id,
            WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
        )
        .options(joinedload(WorkflowTask.node))
    )


def _to_out(
    db: Session,
    contract: Contract,
    current_user: User,
    creator_name: str = "",
) -> ContractOut:
    out = ContractOut.model_validate(contract)
    out.creator_name = creator_name
    if contract.workflow_instance_id is not None:
        instance = db.get(WorkflowInstance, contract.workflow_instance_id)
        out.workflow_version = instance.workflow_version.version if instance is not None else None
    task = _active_task_for_contract(db, contract)
    if task is not None:
        out.active_task = {
            "id": task.id,
            "node_code": task.node.code,
            "node_name": task.node.name,
            "position_code": task.required_position_code,
            "position_name": task.node.name,
        }
        out.can_act = task_is_actionable_by(db, task, current_user)
    return out


def _permission_contexts(db: Session, user: User, contract: Contract | None = None):
    return (PermissionContext(
        company_code="investment",
        participant_ids=frozenset({user.id}),
        assigned_user_id=user.id,
    ),) + tuple(
        PermissionContext(
            company_code=assignment.organization.company_code,
            department_code=(
                assignment.organization.code
                if assignment.organization.organization_type.value == "department"
                else None
            ),
            assigned_user_id=user.id,
            participant_ids=frozenset({user.id}),
        )
        for assignment in active_assignments(db, user.id)
    )


def _has_contract_permission(
    db: Session, user: User, permission_code: str, contract: Contract | None = None
) -> bool:
    return any(
        has_permission(db, user, permission_code, context)
        for context in _permission_contexts(db, user, contract)
    )


def _visible_contract_ids(db: Session, user: User) -> set[int] | None:
    """Compatibility helper for callers that still consume an id set."""
    if not _has_contract_permission(db, user, "investment.legal.contracts.view"):
        raise HTTPException(status_code=403, detail="权限不足")
    scope = legal_record_scope(db, user)
    if scope.global_access:
        return None
    return set(db.scalars(
        select(Contract.id).where(contract_access_predicate(scope))
    ))


def _ensure_contract_visible(db: Session, contract: Contract, user: User) -> None:
    if not _has_contract_permission(db, user, "investment.legal.contracts.view", contract):
        raise HTTPException(status_code=404, detail="合同不存在")
    if not can_access_contract(db, contract, legal_record_scope(db, user)):
        raise HTTPException(status_code=404, detail="合同不存在")


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


def _complete_current_task(
    db: Session,
    contract: Contract,
    current_user: User,
    action: WorkflowAction,
    comment: str,
) -> ContractOut:
    task = _active_task_for_contract(db, contract)
    if task is None:
        raise HTTPException(status_code=422, detail="合同没有可处理的当前工作流任务")
    try:
        complete_task(db, task.id, current_user, action, comment)
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
    db.refresh(contract)
    return _to_out(db, contract, current_user, current_user.full_name)


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #
@router.get("", response_model=Response[list[ContractOut]], summary="合同列表")
def list_contracts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """公司范围岗位见全部供管合同，外聘法律顾问仅见被指定合同。"""
    if not _has_contract_permission(db, current_user, "investment.legal.contracts.view"):
        raise HTTPException(status_code=403, detail="权限不足")
    stmt = select(Contract).where(
        contract_access_predicate(legal_record_scope(db, current_user))
    ).order_by(Contract.id.desc())
    rows = db.scalars(stmt).all()
    names = _names_map(db, {c.created_by for c in rows})
    return Response.ok([_to_out(db, c, current_user, names.get(c.created_by, "")) for c in rows])


@router.get("/export", summary="导出合同列表(CSV)")
def export_contracts(
    db: Session = Depends(get_db),
    current_user: User = Depends(_export_guard),
):
    rows = db.scalars(
        select(Contract)
        .where(contract_access_predicate(legal_record_scope(db, current_user)))
        .order_by(Contract.id.desc())
    ).all()
    content = io.StringIO()
    writer = csv.writer(content)
    writer.writerow([
        "合同编号", "合同名称", "合同类型", "是否内部合同", "合同标的", "签订日期",
        "客户社会信用代码", "客户名称", "合同金额", "币种", "付款条件",
    ])
    for contract in rows:
        writer.writerow([_csv_cell(value) for value in (
            contract.contract_no,
            contract.title,
            contract.contract_type,
            "是" if contract.is_internal else "否",
            contract.subject,
            contract.sign_date,
            contract.customer_credit_code,
            contract.customer_name,
            contract.amount,
            contract.currency,
            contract.payment_terms,
        )])
    data = ("\ufeff" + content.getvalue()).encode("utf-8")
    filename = quote("合同列表.csv")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/todo", response_model=Response[list[ContractOut]], summary="待我审批的合同")
def list_todo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _has_contract_permission(db, current_user, "investment.legal.contracts.view"):
        raise HTTPException(status_code=403, detail="权限不足")
    tasks = my_active_tasks(db, current_user, WorkflowTargetType.CONTRACT)
    contract_ids = [task.instance.target_id for task in tasks]
    rows_by_id = {
        contract.id: contract
        for contract in db.scalars(select(Contract).where(Contract.id.in_(contract_ids)))
    }
    rows = [rows_by_id[contract_id] for contract_id in contract_ids if contract_id in rows_by_id]
    scope = legal_record_scope(db, current_user)
    rows = [row for row in rows if can_access_contract(db, row, scope)]
    names = _names_map(db, {c.created_by for c in rows})
    return Response.ok([_to_out(db, c, current_user, names.get(c.created_by, "")) for c in rows])


@router.get("/{contract_id}", response_model=Response[ContractOut], summary="合同详情")
def get_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_contract_visible(db, contract, current_user)
    names = _names_map(db, {contract.created_by})
    return Response.ok(_to_out(db, contract, current_user, names.get(contract.created_by, "")))


@router.get(
    "/{contract_id}/approvals",
    response_model=Response[list[ApprovalOut]],
    summary="合同审批流转记录（审计日志）",
)
def list_approvals(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_contract_visible(db, contract, current_user)
    rows = db.scalars(
        select(Approval)
        .where(Approval.contract_id == contract_id)
        .order_by(Approval.id.asc())  # 按时间正序，便于时间轴展示
    ).all()
    names = _names_map(db, {a.approver_id for a in rows})
    out = []
    for a in rows:
        item = ApprovalOut.model_validate(a)
        item.approver_name = names.get(a.approver_id, "")
        out.append(item)
    return Response.ok(out)


# --------------------------------------------------------------------------- #
# 录入 / 修改 / 删除（业务经办）
# --------------------------------------------------------------------------- #
@router.post(
    "",
    response_model=Response[ContractOut],
    summary="新建合同(业务经办)",
    dependencies=[Depends(_create_guard)],
)
def create_contract(
    payload: ContractCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if db.scalar(select(Contract).where(Contract.contract_no == payload.contract_no)):
        raise HTTPException(status_code=400, detail="合同编号已存在")
    try:
        ownership = resolve_legal_ownership(
            db,
            current_user,
            "contract",
            payload.initiator_assignment_id,
            payload.organization_code,
        )
    except LegalOwnershipError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    contract = Contract(
        **payload.model_dump(exclude={"initiator_assignment_id", "organization_code"}),
        company_code=ownership.company_code,
        organization_code=ownership.organization_code,
        initiator_assignment_id=ownership.initiator_assignment_id,
        workflow_route_version=1,
        status=ContractStatus.DRAFT,
        current_step=0,
        created_by=current_user.id,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return Response.ok(_to_out(db, contract, current_user, current_user.full_name))


@router.put(
    "/{contract_id}",
    response_model=Response[ContractOut],
    summary="修改合同(业务经办，仅草稿/驳回态)",
    dependencies=[Depends(_update_guard)],
)
def update_contract(
    contract_id: int,
    payload: ContractUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_contract_visible(db, contract, current_user)
    if contract.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能修改本人创建的合同")
    if contract.status not in (ContractStatus.DRAFT, ContractStatus.REJECTED):
        raise HTTPException(status_code=400, detail="当前状态不可修改")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contract, field, value)
    db.commit()
    db.refresh(contract)
    return Response.ok(_to_out(db, contract, current_user, current_user.full_name))


@router.delete(
    "/{contract_id}",
    response_model=Response[dict],
    summary="删除合同(仅本人草稿/驳回态；已审批记录不可删除)",
)
def delete_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = db.scalar(
        select(Contract)
        .where(Contract.id == contract_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="合同不存在")

    if contract.status == ContractStatus.APPROVED:
        raise HTTPException(status_code=409, detail="已审批业务记录不可删除")
    _ensure_contract_visible(db, contract, current_user)
    if not _has_contract_permission(
        db, current_user, "investment.legal.contracts.delete", contract
    ):
        raise HTTPException(status_code=403, detail="权限不足")

    # 其余状态：仅本人创建且仅草稿/被驳回可删；审批中(pending)不可删
    if contract.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能删除本人创建的合同")
    if contract.status not in (ContractStatus.DRAFT, ContractStatus.REJECTED):
        raise HTTPException(status_code=400, detail="仅草稿或被驳回的合同可删除")
    cancel_active_workflow_for_target(
        db,
        WorkflowTargetType.CONTRACT,
        contract.id,
    )
    db.delete(contract)
    db.commit()
    return Response.ok({"id": contract_id})


# --------------------------------------------------------------------------- #
# 审批流：提交 / 逐级通过 / 驳回
# --------------------------------------------------------------------------- #
@router.post(
    "/{contract_id}/submit",
    response_model=Response[ContractOut],
    summary="提交审批(业务经办)",
    dependencies=[Depends(_submit_guard)],
)
def submit_contract(
    contract_id: int,
    payload: WorkflowStartRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_contract_visible(db, contract, current_user)
    enabled_superuser = bool(current_user.is_active and current_user.is_superuser)
    if contract.created_by != current_user.id and not (
        contract.workflow_instance_id is not None and enabled_superuser
    ):
        raise HTTPException(status_code=403, detail="只能提交本人创建的合同")
    if contract.workflow_instance_id is not None:
        instance = db.get(WorkflowInstance, contract.workflow_instance_id)
        task = _active_task_for_contract(db, contract)
        if instance is None or (
            instance.submitted_by != current_user.id and not enabled_superuser
        ):
            raise HTTPException(status_code=403, detail="只能由原提交人重新提交合同")
        if task is None or not task.node.auto_complete_on_submit:
            raise HTTPException(status_code=422, detail="合同当前不处于业务经办重提环节")
        return Response.ok(_complete_current_task(
            db, contract, current_user, WorkflowAction.SUBMIT, "重新提交审批"
        ))
    try:
        workflow_code = (
            contract_workflow_code(contract)
            if contract.workflow_route_version >= 1
            else None
        )
        start_workflow(
            db,
            WorkflowTargetType.CONTRACT,
            contract.id,
            current_user,
            payload.designated_users if payload is not None else {},
            workflow_code=workflow_code,
        )
        db.commit()
    except WorkflowValidationError as error:
        db.rollback()
        raise _workflow_error(error) from error
    db.refresh(contract)
    return Response.ok(_to_out(db, contract, current_user, current_user.full_name))


@router.post(
    "/{contract_id}/approve",
    response_model=Response[ContractOut],
    summary="逐级审批通过（当前环节角色）",
)
def approve_contract(
    contract_id: int,
    payload: ApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_contract_visible(db, contract, current_user)
    if not any(
        _has_contract_permission(db, current_user, permission_code, contract)
        for permission_code in (
            "investment.legal.contracts.review",
            "investment.legal.contracts.approve",
        )
    ):
        raise HTTPException(status_code=403, detail="权限不足")
    return Response.ok(_complete_current_task(
        db, contract, current_user, WorkflowAction.APPROVE, payload.comment.strip()
    ))


@router.post(
    "/{contract_id}/reject",
    response_model=Response[ContractOut],
    summary="退回（原因必填，当前工作流任务）",
)
def reject_contract(
    contract_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_contract_visible(db, contract, current_user)
    if not _has_contract_permission(
        db, current_user, "investment.legal.contracts.return", contract
    ):
        raise HTTPException(status_code=403, detail="权限不足")
    return Response.ok(_complete_current_task(
        db, contract, current_user, WorkflowAction.RETURN, payload.comment.strip()
    ))


# --------------------------------------------------------------------------- #
# 合同附件：真实上传 / 下载
# --------------------------------------------------------------------------- #
def _attachment_dir(contract_id: int) -> Path:
    return Path(settings.UPLOAD_DIR) / f"contract_{contract_id}"


@router.post(
    "/{contract_id}/attachment",
    response_model=Response[ContractOut],
    summary="上传合同附件(业务经办，覆盖式单附件)",
    dependencies=[Depends(_update_guard)],
)
async def upload_attachment(
    contract_id: int,
    file: UploadFile = File(..., description="合同附件 PDF/Word/Excel/图片，≤20MB"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_contract_visible(db, contract, current_user)
    if contract.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能为本人创建的合同上传附件")
    fname = file.filename or "附件"
    ext = Path(fname).suffix.lower()
    if ext not in _ATTACH_EXT:
        raise HTTPException(status_code=400, detail="不支持的附件格式（仅 PDF/Word/Excel/图片）")
    content = await file.read()
    if len(content) > _ATTACH_MAX_BYTES:
        raise HTTPException(status_code=400, detail="附件超过 20MB 上限")

    d = _attachment_dir(contract_id)
    d.mkdir(parents=True, exist_ok=True)
    # 覆盖式：删除旧附件文件
    if contract.attachment_stored:
        old = d / contract.attachment_stored
        try:
            if old.exists():
                old.unlink()
        except OSError:
            pass
    stored = f"{uuid.uuid4().hex}{ext}"
    (d / stored).write_bytes(content)
    contract.attachment_name = fname
    contract.attachment_stored = stored
    db.commit()
    db.refresh(contract)
    names = _names_map(db, {contract.created_by})
    return Response.ok(
        _to_out(db, contract, current_user, names.get(contract.created_by, "")),
        message="附件上传成功",
    )


# 合同附件/法律文书 下载角色：业务经办/业务复核/法务风控/财务经办/供管负责人/投资总经理/法律顾问 + 超管
# (仅财务复核不可下载)
_contract_dl_guard = _view_guard


@router.get("/{contract_id}/attachment", summary="下载合同附件原件(除财务复核)")
def download_attachment(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_contract_dl_guard),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_contract_visible(db, contract, current_user)
    if not contract.attachment_stored:
        raise HTTPException(status_code=404, detail="该合同暂无附件")
    path = _attachment_dir(contract_id) / contract.attachment_stored
    if not path.exists():
        raise HTTPException(status_code=404, detail="附件文件缺失")
    return FileResponse(str(path), filename=contract.attachment_name or contract.attachment_stored)


# --------------------------------------------------------------------------- #
# 法律文件审批表(.docx，严格 3cm 行高 + 方正小标宋简体/仿宋_GB2312)
# --------------------------------------------------------------------------- #
@router.get("/{contract_id}/legal-doc", summary="生成并下载法律文件审批表(.docx，除财务复核)")
def download_legal_doc(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_contract_dl_guard),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_contract_visible(db, contract, current_user)
    creator = _names_map(db, {contract.created_by}).get(contract.created_by, "")

    approvals = db.scalars(
        select(Approval).where(Approval.contract_id == contract_id).order_by(Approval.id.asc())
    ).all()
    ap_names = _names_map(db, {a.approver_id for a in approvals})
    # 每个意见栏取该岗位最近一次审批记录（id 升序 → 后者覆盖）：
    #   意见渲染其“实际审批意见”(comment，不再默认“同意”)，签名取电子签名快照。
    opinions: dict[str, dict] = {}
    for a in approvals:
        opinion_position = a.position_code
        if not opinion_position:
            opinion_position = legal_doc_svc.HISTORICAL_OPINION_POSITIONS.get(a.approver_role)
        if opinion_position in _OPINION_POSITIONS:
            opinions[opinion_position] = {
                "comment": a.comment or "",                    # 实际审批意见，空则留空
                "approver_name": ap_names.get(a.approver_id, ""),
                "signature": a.signature_snapshot or "",       # 电子签名快照(data-URI)
                "date": str(a.created_at)[:10] if a.created_at else "",
            }

    data = legal_doc_svc.build_legal_doc(
        {
            "title": contract.title,
            "contract_no": contract.contract_no,
            "sign_date": str(contract.sign_date) if contract.sign_date else "",
            "creator_name": creator,
        },
        opinions,
    )
    fname = quote(f"法律文件审批表_{contract.contract_no}.docx")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=_DOCX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )


# --------------------------------------------------------------------------- #
# AI 合同审查（DeepSeek + 法规知识库；接口永不 500）
# --------------------------------------------------------------------------- #
def _contract_text_for_review(contract: Contract) -> tuple[str, bool]:
    """构造待审查合同文本：优先用已上传附件提取全文；无附件则用结构化字段兜底。

    返回 (text, has_attachment_text)。
    """
    if contract.attachment_stored:
        path = _attachment_dir(contract.id) / contract.attachment_stored
        if path.exists():
            try:
                _ft, pages = research_svc.extract_pages(contract.attachment_name or "", path.read_bytes())
                text = "\n".join(p.get("text", "") for p in pages).strip()
                if text:
                    return text, True
            except Exception:  # noqa: BLE001 .doc/扫描件等无法提取 → 走字段兜底
                pass
    # 兜底：用合同结构化字段拼出可审查文本
    fields = [
        f"合同名称：{contract.title}",
        f"合同编号：{contract.contract_no}",
        f"甲方：{contract.party_a or '未填写'}",
        f"乙方：{contract.party_b or '未填写'}",
        f"合同类型：{contract.contract_type or '未填写'}",
        f"是否内部合同：{'是' if contract.is_internal else '否'}",
        f"合同标的：{contract.subject or '未填写'}",
        f"客户名称：{contract.customer_name or '未填写'}",
        f"合同金额：{contract.amount} {contract.currency or ''}",
        f"付款条件：{contract.payment_terms or '未填写'}",
        f"备注：{contract.remark or '无'}",
    ]
    return "\n".join(fields), False


@router.post("/{contract_id}/ai-review", response_model=Response[dict], summary="AI 合同审查(DeepSeek+法规知识库)")
def ai_review_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_view_guard),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_contract_visible(db, contract, current_user)
    contract_text, has_attachment = _contract_text_for_review(contract)
    structured_fields = {
        "contract_no": contract.contract_no,
        "title": contract.title,
        "party_a": contract.party_a,
        "party_b": contract.party_b,
        "amount": str(contract.amount) if contract.amount is not None else "",
        "sign_date": str(contract.sign_date) if contract.sign_date else "",
        "contract_type": contract.contract_type,
        "customer_name": contract.customer_name,
        "subject": contract.subject,
        "currency": contract.currency,
        "payment_terms": contract.payment_terms,
        "remark": contract.remark,
        "is_internal": contract.is_internal,
    }
    try:
        evidence = retrieve_evidence(db, contract_text)
        findings = deterministic_findings(contract_text, structured_fields, evidence)
        result = review_with_evidence(contract_text, structured_fields, evidence, findings)
    except Exception as exc:  # noqa: BLE001 - local retrieval must never break review endpoint
        # Keep the endpoint available if the knowledge store is temporarily
        # unavailable; deterministic checks still provide a safe fallback.
        evidence = []
        try:
            findings = deterministic_findings(contract_text, structured_fields, evidence)
        except Exception:  # noqa: BLE001
            findings = []
        count = len(findings)
        result = {
            "fact_checks": findings,
            "risk_findings": [],
            "coverage": {"claim_count": count, "supported_count": 0, "contradicted_count": sum(f.get("verdict") == "contradicted" for f in findings), "not_found_count": sum(f.get("verdict") == "not_found" for f in findings), "evidence_rate": 0},
            "engine": "rule",
            "fallback_reason": "provider_error",
        }
    kb_titles: list[str] = []
    for chunk in evidence:
        if chunk.title and chunk.title not in kb_titles:
            kb_titles.append(chunk.title)
    return Response.ok({
        "markdown": render_review_markdown(result),
        "engine": result["engine"],
        "has_attachment": has_attachment,
        "kb_used": kb_titles,
        "retrieved_sources": [
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "category": chunk.category,
                "section": chunk.section,
                "ordinal": chunk.ordinal,
                "text": chunk.text,
            }
            for chunk in evidence
        ],
        "fact_checks": result.get("fact_checks", []),
        "risk_findings": result.get("risk_findings", []),
        "coverage": result.get("coverage", {}),
        "fallback_reason": result.get("fallback_reason"),
    })
