"""审批中心端点 —— 两套独立审批单工作流（业务付款审批单 / 业务审批单）。

与合同模块（/contracts）完全独立：本模块管理「审批单」的全生命周期与逐级审批流，
审批链按 form_type 分派（enums.PAYMENT_APPROVAL_CHAIN / BUSINESS_APPROVAL_CHAIN）。

流程与合同审批一致：业务经办创建草稿→提交(自动完成第0级+电子签名)→逐级通过/驳回。
附加能力：
- 打印导出：服务端填充原始 xlsx 模板（/print）。
- AI 合同校对：审批单附件 ⇄ 合同管理原件文本比对（/proofread）。
"""
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
    CompanyCode,
    ContractStatus,
    ContractType,
    WorkflowAction,
    WorkflowTargetType,
    WorkflowTaskStatus,
)
from app.db.session import get_db
from app.models.approval_form import ApprovalForm, ApprovalFormAction
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.user import User
from app.models.workflow import WorkflowInstance, WorkflowTask
from app.schemas.approval_form import (
    ApprovalFormActionOut,
    ApprovalFormCreate,
    ApprovalFormOut,
    ApprovalFormUpdate,
    ApproveRequest,
    RejectRequest,
)
from app.schemas.common import Response
from app.schemas.workflow import WorkflowStartRequest
from app.services import approval_print as print_svc
from app.services import approval_proofread as proof_svc
from app.services import customer_research as research_svc
from app.services.num_cn import amount_to_cn
from app.services.assignment_permissions import PermissionContext, has_permission, has_position
from app.services.workflow_engine import (
    WorkflowTaskConflict,
    WorkflowValidationError,
    complete_task,
    my_active_tasks,
    start_workflow,
    task_is_actionable_by,
)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ATTACH_MAX_BYTES = 20 * 1024 * 1024  # ≤ 20MB

router = APIRouter()

_supply_context = lambda: PermissionContext(company_code=CompanyCode.SUPPLY_MANAGEMENT.value)
_view_guard = require_permission("supply.approval.view", _supply_context)
_create_guard = require_permission("supply.approval.create", _supply_context)
_update_guard = require_permission("supply.approval.update", _supply_context)
_delete_guard = require_permission("supply.approval.delete", _supply_context)
_submit_guard = require_permission("supply.approval.submit", _supply_context)
_export_guard = require_permission("supply.approval.export", _supply_context)


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _get_form_or_404(db: Session, form_id: int) -> ApprovalForm:
    form = db.get(ApprovalForm, form_id)
    if not form:
        raise HTTPException(status_code=404, detail="审批单不存在")
    return form


def _names_map(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all()
    return {i: n for i, n in rows}


def _active_task_for_form(db: Session, form: ApprovalForm) -> WorkflowTask | None:
    if form.workflow_instance_id is None:
        return None
    return db.scalar(
        select(WorkflowTask)
        .where(
            WorkflowTask.instance_id == form.workflow_instance_id,
            WorkflowTask.status == WorkflowTaskStatus.ACTIVE,
        )
        .options(joinedload(WorkflowTask.node))
    )


def _to_out(
    db: Session,
    form: ApprovalForm,
    current_user: User,
    creator_name: str = "",
) -> ApprovalFormOut:
    out = ApprovalFormOut.model_validate(form)
    out.creator_name = creator_name
    if form.workflow_instance_id is not None:
        instance = db.get(WorkflowInstance, form.workflow_instance_id)
        out.workflow_version = instance.workflow_version.version if instance is not None else None
    task = _active_task_for_form(db, form)
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
    form: ApprovalForm,
    current_user: User,
    action: WorkflowAction,
    comment: str,
) -> ApprovalFormOut:
    task = _active_task_for_form(db, form)
    if task is None:
        raise HTTPException(status_code=422, detail="审批单没有可处理的当前工作流任务")
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
    db.refresh(form)
    return _to_out(db, form, current_user, current_user.full_name)


def _apply_payload(form: ApprovalForm, data: dict, db: Session) -> None:
    """写入字段：付款单自动生成大写金额；客户外键联动快照客户名称。"""
    for field, value in data.items():
        setattr(form, field, value)
    # 客户外键 → 快照客户名称（若前端未同时传 customer_name）
    if "customer_id" in data and data["customer_id"] and not data.get("customer_name"):
        cust = db.get(Customer, data["customer_id"])
        if cust:
            form.customer_name = cust.name
    # 付款审批单：自动大写金额；业务审批单金额归零
    if form.form_type == ContractType.PAYMENT:
        form.amount_words = amount_to_cn(form.amount or 0)
    else:
        form.amount = 0
        form.amount_words = ""


def _attachment_dir(form_id: int) -> Path:
    return Path(settings.UPLOAD_DIR) / f"approval_form_{form_id}"


def _extract_attachment_text(name: str, path: Path) -> str:
    """从附件提取纯文本（pdf/docx/xlsx）；失败返回空串。"""
    if not path.exists():
        return ""
    try:
        _ft, pages = research_svc.extract_pages(name or "", path.read_bytes())
        return "\n".join(p.get("text", "") for p in pages).strip()
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #
@router.get("", response_model=Response[list[ApprovalFormOut]], summary="审批单列表", dependencies=[Depends(_view_guard)])
def list_forms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """业务经办仅见本人；其余角色（审批/监督方）见全部。"""
    stmt = select(ApprovalForm).order_by(ApprovalForm.id.desc())
    if has_position(db, current_user.id, "supply.business_handler"):
        stmt = stmt.where(ApprovalForm.created_by == current_user.id)
    rows = db.scalars(stmt).all()
    names = _names_map(db, {f.created_by for f in rows})
    return Response.ok([
        _to_out(db, f, current_user, names.get(f.created_by, "")) for f in rows
    ])


@router.get("/todo", response_model=Response[list[ApprovalFormOut]], summary="待我审批的单据", dependencies=[Depends(_view_guard)])
def list_todo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tasks = my_active_tasks(db, current_user)
    form_tasks = [task for task in tasks if task.instance.target_type in {
        WorkflowTargetType.PAYMENT_APPROVAL,
        WorkflowTargetType.BUSINESS_APPROVAL,
    }]
    form_ids = [task.instance.target_id for task in form_tasks]
    rows_by_id = {
        form.id: form
        for form in db.scalars(select(ApprovalForm).where(ApprovalForm.id.in_(form_ids)))
    }
    rows = [rows_by_id[form_id] for form_id in form_ids if form_id in rows_by_id]
    names = _names_map(db, {f.created_by for f in rows})
    return Response.ok([
        _to_out(db, f, current_user, names.get(f.created_by, "")) for f in rows
    ])


@router.get("/{form_id}", response_model=Response[ApprovalFormOut], summary="审批单详情", dependencies=[Depends(_view_guard)])
def get_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    names = _names_map(db, {form.created_by})
    return Response.ok(_to_out(db, form, current_user, names.get(form.created_by, "")))


@router.get(
    "/{form_id}/actions",
    response_model=Response[list[ApprovalFormActionOut]],
    summary="审批流转记录（审计日志）",
    dependencies=[Depends(_view_guard)],
)
def list_actions(
    form_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_form_or_404(db, form_id)
    rows = db.scalars(
        select(ApprovalFormAction)
        .where(ApprovalFormAction.form_id == form_id)
        .order_by(ApprovalFormAction.id.asc())
    ).all()
    names = _names_map(db, {a.approver_id for a in rows})
    out = []
    for a in rows:
        item = ApprovalFormActionOut.model_validate(a)
        item.approver_name = names.get(a.approver_id, "")
        out.append(item)
    return Response.ok(out)


# --------------------------------------------------------------------------- #
# 录入 / 修改 / 删除（业务经办）
# --------------------------------------------------------------------------- #
@router.post(
    "",
    response_model=Response[ApprovalFormOut],
    summary="新建审批单(业务经办)",
    dependencies=[Depends(_create_guard)],
)
def create_form(
    payload: ApprovalFormCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = ApprovalForm(
        form_type=payload.form_type,
        status=ContractStatus.DRAFT,
        current_step=0,
        created_by=current_user.id,
    )
    _apply_payload(form, payload.model_dump(exclude={"form_type"}), db)
    db.add(form)
    db.commit()
    db.refresh(form)
    return Response.ok(
        _to_out(db, form, current_user, current_user.full_name), message="审批单已创建"
    )


@router.put(
    "/{form_id}",
    response_model=Response[ApprovalFormOut],
    summary="修改审批单(业务经办，仅草稿/驳回态)",
    dependencies=[Depends(_update_guard)],
)
def update_form(
    form_id: int,
    payload: ApprovalFormUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    if form.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能修改本人创建的审批单")
    if form.status not in (ContractStatus.DRAFT, ContractStatus.REJECTED):
        raise HTTPException(status_code=400, detail="当前状态不可修改")
    _apply_payload(form, payload.model_dump(exclude_unset=True), db)
    db.commit()
    db.refresh(form)
    return Response.ok(
        _to_out(db, form, current_user, current_user.full_name), message="审批单已更新"
    )


@router.delete(
    "/{form_id}",
    response_model=Response[dict],
    summary="删除审批单(仅本人草稿/驳回态；已审批记录不可删除)",
)
def delete_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    if form.status == ContractStatus.APPROVED:
        raise HTTPException(status_code=409, detail="已审批业务记录不可删除")
    if not has_permission(db, current_user, "supply.approval.delete", _supply_context()):
        raise HTTPException(status_code=403, detail="权限不足")
    if form.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能删除本人创建的审批单")
    if form.status not in (ContractStatus.DRAFT, ContractStatus.REJECTED):
        raise HTTPException(status_code=400, detail="仅草稿或被驳回的审批单可删除")
    db.delete(form)
    db.commit()
    return Response.ok({"id": form_id}, message="审批单已删除")


# --------------------------------------------------------------------------- #
# 审批流：提交 / 逐级通过 / 驳回
# --------------------------------------------------------------------------- #
@router.post(
    "/{form_id}/submit",
    response_model=Response[ApprovalFormOut],
    summary="提交审批(业务经办)",
    dependencies=[Depends(_submit_guard)],
)
def submit_form(
    form_id: int,
    payload: WorkflowStartRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    enabled_superuser = bool(current_user.is_active and current_user.is_superuser)
    if form.created_by != current_user.id and not (
        form.workflow_instance_id is not None and enabled_superuser
    ):
        raise HTTPException(status_code=403, detail="只能提交本人创建的审批单")
    if form.workflow_instance_id is not None:
        instance = db.get(WorkflowInstance, form.workflow_instance_id)
        task = _active_task_for_form(db, form)
        if instance is None or (
            instance.submitted_by != current_user.id and not enabled_superuser
        ):
            raise HTTPException(status_code=403, detail="只能由原提交人重新提交审批单")
        if task is None or not task.node.auto_complete_on_submit:
            raise HTTPException(status_code=422, detail="审批单当前不处于业务经办重提环节")
        return Response.ok(
            _complete_current_task(
                db, form, current_user, WorkflowAction.SUBMIT, "重新提交审批"
            ),
            message="已提交审批",
        )
    target_type = (
        WorkflowTargetType.PAYMENT_APPROVAL
        if form.form_type == ContractType.PAYMENT
        else WorkflowTargetType.BUSINESS_APPROVAL
    )
    try:
        start_workflow(
            db,
            target_type,
            form.id,
            current_user,
            payload.designated_users if payload is not None else {},
        )
        db.commit()
    except WorkflowValidationError as error:
        db.rollback()
        raise _workflow_error(error) from error
    db.refresh(form)
    return Response.ok(
        _to_out(db, form, current_user, current_user.full_name), message="已提交审批"
    )


@router.post(
    "/{form_id}/approve",
    response_model=Response[ApprovalFormOut],
    summary="逐级审批通过（当前环节角色）",
)
def approve_form(
    form_id: int,
    payload: ApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    return Response.ok(
        _complete_current_task(
            db, form, current_user, WorkflowAction.APPROVE, payload.comment.strip()
        ),
        message="已通过",
    )


@router.post(
    "/{form_id}/reject",
    response_model=Response[ApprovalFormOut],
    summary="驳回（原因必填，当前环节角色）",
)
def reject_form(
    form_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    return Response.ok(
        _complete_current_task(
            db, form, current_user, WorkflowAction.RETURN, payload.comment
        ),
        message="已退回",
    )


# --------------------------------------------------------------------------- #
# 合同附件：上传 / 下载（PDF）
# --------------------------------------------------------------------------- #
@router.post(
    "/{form_id}/attachment",
    response_model=Response[ApprovalFormOut],
    summary="上传合同附件(业务经办，PDF，覆盖式)",
    dependencies=[Depends(_update_guard)],
)
async def upload_attachment(
    form_id: int,
    file: UploadFile = File(..., description="合同附件 PDF，≤20MB"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    if form.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能为本人创建的审批单上传附件")
    fname = file.filename or "附件"
    ext = Path(fname).suffix.lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="合同附件仅支持 PDF 格式")
    content = await file.read()
    if len(content) > _ATTACH_MAX_BYTES:
        raise HTTPException(status_code=400, detail="附件超过 20MB 上限")

    d = _attachment_dir(form_id)
    d.mkdir(parents=True, exist_ok=True)
    if form.attachment_stored:
        old = d / form.attachment_stored
        try:
            if old.exists():
                old.unlink()
        except OSError:
            pass
    stored = f"{uuid.uuid4().hex}{ext}"
    (d / stored).write_bytes(content)
    form.attachment_name = fname
    form.attachment_stored = stored
    db.commit()
    db.refresh(form)
    names = _names_map(db, {form.created_by})
    return Response.ok(
        _to_out(db, form, current_user, names.get(form.created_by, "")),
        message="附件上传成功",
    )


# 业务审批单附件/打印 下载角色：全部非法律顾问 + 超管
_approval_dl_guard = _export_guard


@router.get("/{form_id}/attachment", summary="下载审批单合同附件原件(非法律顾问)")
def download_attachment(
    form_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_approval_dl_guard),
):
    form = _get_form_or_404(db, form_id)
    if not form.attachment_stored:
        raise HTTPException(status_code=404, detail="该审批单暂无附件")
    path = _attachment_dir(form_id) / form.attachment_stored
    if not path.exists():
        raise HTTPException(status_code=404, detail="附件文件缺失")
    return FileResponse(str(path), filename=form.attachment_name or form.attachment_stored)


# --------------------------------------------------------------------------- #
# 打印导出（填充原始 xlsx 模板）
# --------------------------------------------------------------------------- #
@router.get("/{form_id}/print", summary="导出审批单(xlsx，格式还原模板，非法律顾问)")
def print_form(
    form_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_approval_dl_guard),
):
    form = _get_form_or_404(db, form_id)
    instance = (
        db.get(WorkflowInstance, form.workflow_instance_id)
        if form.workflow_instance_id is not None
        else None
    )
    legacy_workflow = form.workflow_instance_id is None or (
        instance is not None and instance.workflow_version.version < 2
    )
    actions = db.scalars(
        select(ApprovalFormAction)
        .where(ApprovalFormAction.form_id == form_id)
        .order_by(ApprovalFormAction.id.asc())
    ).all()
    ap_names = _names_map(db, {a.approver_id for a in actions})
    # 每级取该 step 最近一次审批动作（id 升序 → 后者覆盖）
    steps: dict[int, dict] = {}
    for a in actions:
        steps[a.step] = {
            "step": a.step,
            "position_code": a.position_code,
            "role": a.approver_role,
            "name": ap_names.get(a.approver_id, ""),
            "comment": a.comment or "",
            "signature": a.signature_snapshot or "",
            "date": str(a.created_at)[:10] if a.created_at else "",
            "action": a.action.value,
        }

    data = print_svc.build_approval_form_xlsx(
        {
            "form_type": form.form_type,
            "legacy_workflow": legacy_workflow,
            "department": form.department,
            "apply_date": form.apply_date,
            "customer_name": form.customer_name,
            "business_type": form.business_type,
            "business_desc": form.business_desc,
            "contract_no": form.contract_no,
            "remark": form.remark,
            "amount": form.amount,
            "amount_words": form.amount_words,
            "bank_name": form.bank_name,
            "bank_account": form.bank_account,
        },
        list(steps.values()),
    )
    label = "业务付款审批单" if form.form_type == ContractType.PAYMENT else "业务审批单"
    fname = quote(f"{label}_{form.contract_no or form.id}.xlsx")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )


# --------------------------------------------------------------------------- #
# AI 合同校对（审批单附件 ⇄ 合同管理原件；接口永不 500）
# --------------------------------------------------------------------------- #
@router.post("/{form_id}/proofread", response_model=Response[dict], summary="AI 合同校对(DeepSeek 文本比对)")
def proofread_form(
    form_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    form = _get_form_or_404(db, form_id)

    # 审批单附件文本
    form_text = ""
    if form.attachment_stored:
        form_text = _extract_attachment_text(
            form.attachment_name, _attachment_dir(form_id) / form.attachment_stored
        )

    # 按合同编号从合同管理模块取对应合同 + 原件文本
    contract = None
    if form.contract_no:
        contract = db.scalar(select(Contract).where(Contract.contract_no == form.contract_no))
    contract_text = ""
    contract_no_matched = ""
    if contract:
        contract_no_matched = contract.contract_no
        if contract.attachment_stored:
            c_dir = Path(settings.UPLOAD_DIR) / f"contract_{contract.id}"
            contract_text = _extract_attachment_text(
                contract.attachment_name, c_dir / contract.attachment_stored
            )

    result = proof_svc.proofread(
        contract_no=form.contract_no or "",
        form_text=form_text,
        contract_found=contract is not None,
        contract_no_matched=contract_no_matched,
        contract_text=contract_text,
    )
    return Response.ok(result)
