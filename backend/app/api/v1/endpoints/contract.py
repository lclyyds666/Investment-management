"""合同全生命周期与岗位工作流兼容端点。"""
import io
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_permission
from app.core.config import settings
from app.core.enums import (
    ContractStatus,
    CompanyCode,
    DataScope,
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
from app.services import contract_review as review_svc
from app.services import customer_research as research_svc
from app.services import legal_doc as legal_doc_svc
from app.services.assignment_permissions import PermissionContext, has_permission, permission_grants
from app.services.workflow_engine import (
    WorkflowTaskConflict,
    WorkflowValidationError,
    complete_task,
    my_active_tasks,
    start_workflow,
    task_is_actionable_by,
)

_OPINION_POSITIONS = {code for code, _ in legal_doc_svc.OPINION_ROLES}
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter()

_supply_context = lambda: PermissionContext(company_code=CompanyCode.SUPPLY_MANAGEMENT.value)
_view_guard = require_permission("supply.contract.view", _supply_context)
_create_guard = require_permission("supply.contract.create", _supply_context)
_update_guard = require_permission("supply.contract.update", _supply_context)
_submit_guard = require_permission("supply.contract.submit", _supply_context)
_export_guard = require_permission("supply.contract.export", _supply_context)

# 合同附件允许的扩展名（与前端 accept 对齐）
_ATTACH_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"}
_ATTACH_MAX_BYTES = 20 * 1024 * 1024  # 单个附件 ≤ 20MB


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


def _assigned_contract_ids(db: Session, user: User) -> set[int]:
    has_assigned_grant = any(
        grant.code == "supply.contract.view" and grant.data_scope == DataScope.ASSIGNED
        for grant in permission_grants(db, user.id)
    )
    if not has_assigned_grant:
        return set()
    return set(db.scalars(
        select(WorkflowInstance.target_id)
        .join(WorkflowTask, WorkflowTask.instance_id == WorkflowInstance.id)
        .where(
            WorkflowInstance.target_type == WorkflowTargetType.CONTRACT,
            WorkflowTask.designated_user_id == user.id,
        )
    ))


def _visible_contract_ids(db: Session, user: User) -> set[int] | None:
    grants = tuple(
        grant for grant in permission_grants(db, user.id)
        if grant.code == "supply.contract.view"
    )
    if any(
        grant.data_scope == DataScope.COMPANY
        and grant.scope_ref == CompanyCode.SUPPLY_MANAGEMENT.value
        for grant in grants
    ):
        return None
    if not any(grant.data_scope == DataScope.ASSIGNED for grant in grants):
        raise HTTPException(status_code=403, detail="权限不足")
    return _assigned_contract_ids(db, user)


def _ensure_contract_visible(db: Session, contract: Contract, user: User) -> None:
    visible_ids = _visible_contract_ids(db, user)
    if visible_ids is not None and contract.id not in visible_ids:
        raise HTTPException(status_code=403, detail="权限不足")


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
    stmt = select(Contract).order_by(Contract.id.desc())
    visible_ids = _visible_contract_ids(db, current_user)
    if visible_ids is not None:
        stmt = stmt.where(Contract.id.in_(visible_ids))
    rows = db.scalars(stmt).all()
    names = _names_map(db, {c.created_by for c in rows})
    return Response.ok([_to_out(db, c, current_user, names.get(c.created_by, "")) for c in rows])


@router.get("/todo", response_model=Response[list[ContractOut]], summary="待我审批的合同")
def list_todo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tasks = my_active_tasks(db, current_user, WorkflowTargetType.CONTRACT)
    contract_ids = [task.instance.target_id for task in tasks]
    rows_by_id = {
        contract.id: contract
        for contract in db.scalars(select(Contract).where(Contract.id.in_(contract_ids)))
    }
    rows = [rows_by_id[contract_id] for contract_id in contract_ids if contract_id in rows_by_id]
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
    contract = Contract(
        **payload.model_dump(),
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
    contract = _get_contract_or_404(db, contract_id)

    if contract.status == ContractStatus.APPROVED:
        raise HTTPException(status_code=409, detail="已审批业务记录不可删除")
    if not has_permission(db, current_user, "supply.contract.delete", _supply_context()):
        raise HTTPException(status_code=403, detail="权限不足")

    # 其余状态：仅本人创建且仅草稿/被驳回可删；审批中(pending)不可删
    if contract.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能删除本人创建的合同")
    if contract.status not in (ContractStatus.DRAFT, ContractStatus.REJECTED):
        raise HTTPException(status_code=400, detail="仅草稿或被驳回的合同可删除")
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
    if contract.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能提交本人创建的合同")
    if contract.workflow_instance_id is not None:
        instance = db.get(WorkflowInstance, contract.workflow_instance_id)
        task = _active_task_for_contract(db, contract)
        if instance is None or instance.submitted_by != current_user.id:
            raise HTTPException(status_code=403, detail="只能由原提交人重新提交合同")
        if task is None or not task.node.auto_complete_on_submit:
            raise HTTPException(status_code=422, detail="合同当前不处于业务经办重提环节")
        return Response.ok(_complete_current_task(
            db, contract, current_user, WorkflowAction.SUBMIT, "重新提交审批"
        ))
    try:
        start_workflow(
            db,
            WorkflowTargetType.CONTRACT,
            contract.id,
            current_user,
            payload.designated_users if payload is not None else {},
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
_contract_dl_guard = _export_guard


@router.get("/{contract_id}/attachment", summary="下载合同附件原件(除财务复核)")
def download_attachment(
    contract_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_contract_dl_guard),
):
    contract = _get_contract_or_404(db, contract_id)
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
    _: User = Depends(_contract_dl_guard),
):
    contract = _get_contract_or_404(db, contract_id)
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
    _: User = Depends(_view_guard),
):
    contract = _get_contract_or_404(db, contract_id)
    contract_text, has_attachment = _contract_text_for_review(contract)
    kb_text, kb_titles = review_svc.aggregate_kb_text(db)
    result = review_svc.review(contract_text, kb_text)
    return Response.ok({
        "markdown": result["markdown"],
        "engine": result["engine"],
        "has_attachment": has_attachment,
        "kb_used": kb_titles,
    })
