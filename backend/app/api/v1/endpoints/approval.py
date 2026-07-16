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
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.enums import (
    ApprovalAction,
    ContractStatus,
    ContractType,
    Role,
    form_chain,
    form_is_final_step,
    form_role_at_step,
)
from app.db.session import get_db
from app.models.approval_form import ApprovalForm, ApprovalFormAction
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.user import User
from app.schemas.approval_form import (
    ApprovalFormActionOut,
    ApprovalFormCreate,
    ApprovalFormOut,
    ApprovalFormUpdate,
    ApproveRequest,
    RejectRequest,
)
from app.schemas.common import Response
from app.services import approval_print as print_svc
from app.services import approval_proofread as proof_svc
from app.services import customer_research as research_svc
from app.services.num_cn import amount_to_cn

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ATTACH_MAX_BYTES = 20 * 1024 * 1024  # ≤ 20MB

router = APIRouter()


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


def _to_out(form: ApprovalForm, creator_name: str = "") -> ApprovalFormOut:
    out = ApprovalFormOut.model_validate(form)
    out.creator_name = creator_name
    return out


def _ensure_current_approver(form: ApprovalForm, user: User) -> Role:
    """校验审批单处于审批中且当前用户是本级审批人（超管放行）。"""
    if form.status != ContractStatus.PENDING:
        raise HTTPException(status_code=400, detail="该审批单当前不处于审批中，无法操作")
    expected = form_role_at_step(form.form_type, form.current_step)
    if expected is None:
        raise HTTPException(status_code=400, detail="审批流状态异常")
    if not user.is_superuser and user.role != expected:
        raise HTTPException(
            status_code=403,
            detail=f"当前审批环节应由【{expected.label}】处理，您无权审批",
        )
    return expected


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
@router.get("", response_model=Response[list[ApprovalFormOut]], summary="审批单列表")
def list_forms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """业务经办仅见本人；其余角色（审批/监督方）见全部。"""
    stmt = select(ApprovalForm).order_by(ApprovalForm.id.desc())
    if not current_user.is_superuser and current_user.role == Role.BUSINESS_HANDLER:
        stmt = stmt.where(ApprovalForm.created_by == current_user.id)
    rows = db.scalars(stmt).all()
    names = _names_map(db, {f.created_by for f in rows})
    return Response.ok([_to_out(f, names.get(f.created_by, "")) for f in rows])


@router.get("/todo", response_model=Response[list[ApprovalFormOut]], summary="待我审批的单据")
def list_todo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.scalars(
        select(ApprovalForm)
        .where(ApprovalForm.status == ContractStatus.PENDING)
        .order_by(ApprovalForm.id.desc())
    ).all()
    todo = [
        f for f in rows
        if current_user.is_superuser or form_role_at_step(f.form_type, f.current_step) == current_user.role
    ]
    names = _names_map(db, {f.created_by for f in todo})
    return Response.ok([_to_out(f, names.get(f.created_by, "")) for f in todo])


@router.get("/{form_id}", response_model=Response[ApprovalFormOut], summary="审批单详情")
def get_form(
    form_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    names = _names_map(db, {form.created_by})
    return Response.ok(_to_out(form, names.get(form.created_by, "")))


@router.get(
    "/{form_id}/actions",
    response_model=Response[list[ApprovalFormActionOut]],
    summary="审批流转记录（审计日志）",
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
    dependencies=[Depends(require_roles(Role.BUSINESS_HANDLER))],
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
    return Response.ok(_to_out(form, current_user.full_name), message="审批单已创建")


@router.put(
    "/{form_id}",
    response_model=Response[ApprovalFormOut],
    summary="修改审批单(业务经办，仅草稿/驳回态)",
    dependencies=[Depends(require_roles(Role.BUSINESS_HANDLER))],
)
def update_form(
    form_id: int,
    payload: ApprovalFormUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    if not current_user.is_superuser and form.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能修改本人创建的审批单")
    if form.status not in (ContractStatus.DRAFT, ContractStatus.REJECTED):
        raise HTTPException(status_code=400, detail="当前状态不可修改")
    _apply_payload(form, payload.model_dump(exclude_unset=True), db)
    db.commit()
    db.refresh(form)
    return Response.ok(_to_out(form, current_user.full_name), message="审批单已更新")


@router.delete(
    "/{form_id}",
    response_model=Response[dict],
    summary="删除审批单(草稿/驳回态由本人删；已通过仅超管可删)",
    dependencies=[Depends(require_roles(Role.BUSINESS_HANDLER))],
)
def delete_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    if form.status == ContractStatus.APPROVED and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="权限不足：仅超级管理员可删除已通过审批单")
    if form.status != ContractStatus.APPROVED:
        if not current_user.is_superuser and form.created_by != current_user.id:
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
    dependencies=[Depends(require_roles(Role.BUSINESS_HANDLER))],
)
def submit_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    if not current_user.is_superuser and form.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能提交本人创建的审批单")
    if form.status not in (ContractStatus.DRAFT, ContractStatus.REJECTED):
        raise HTTPException(status_code=400, detail="仅草稿或被驳回的审批单可提交")

    # 清理旧流转记录（重新提交时避免残留），第 0 级随提交自动完成
    db.query(ApprovalFormAction).filter(ApprovalFormAction.form_id == form.id).delete()
    db.add(
        ApprovalFormAction(
            form_id=form.id,
            approver_id=current_user.id,
            step=0,
            approver_role=Role.BUSINESS_HANDLER.value,
            action=ApprovalAction.APPROVE,
            comment="提交审批（业务经办）",
            signature_snapshot=current_user.signature,
        )
    )
    form.status = ContractStatus.PENDING
    form.current_step = 1
    db.commit()
    db.refresh(form)
    return Response.ok(_to_out(form, current_user.full_name), message="已提交审批")


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
    _ensure_current_approver(form, current_user)

    step = form.current_step
    db.add(
        ApprovalFormAction(
            form_id=form.id,
            approver_id=current_user.id,
            step=step,
            approver_role=current_user.role.value,
            action=ApprovalAction.APPROVE,
            comment=payload.comment or "",
            signature_snapshot=current_user.signature,  # 自动电子签章
        )
    )
    if form_is_final_step(form.form_type, step):
        form.status = ContractStatus.APPROVED
    else:
        form.current_step = step + 1
    db.commit()
    db.refresh(form)
    return Response.ok(_to_out(form, current_user.full_name), message="已通过")


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
    _ensure_current_approver(form, current_user)

    db.add(
        ApprovalFormAction(
            form_id=form.id,
            approver_id=current_user.id,
            step=form.current_step,
            approver_role=current_user.role.value,
            action=ApprovalAction.REJECT,
            comment=payload.comment,
            signature_snapshot=None,
        )
    )
    form.status = ContractStatus.REJECTED
    db.commit()
    db.refresh(form)
    return Response.ok(_to_out(form, current_user.full_name), message="已驳回")


# --------------------------------------------------------------------------- #
# 合同附件：上传 / 下载（PDF）
# --------------------------------------------------------------------------- #
@router.post(
    "/{form_id}/attachment",
    response_model=Response[ApprovalFormOut],
    summary="上传合同附件(业务经办，PDF，覆盖式)",
    dependencies=[Depends(require_roles(Role.BUSINESS_HANDLER))],
)
async def upload_attachment(
    form_id: int,
    file: UploadFile = File(..., description="合同附件 PDF，≤20MB"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
    if not current_user.is_superuser and form.created_by != current_user.id:
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
    return Response.ok(_to_out(form, names.get(form.created_by, "")), message="附件上传成功")


@router.get("/{form_id}/attachment", summary="下载审批单合同附件原件")
def download_attachment(
    form_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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
@router.get("/{form_id}/print", summary="导出审批单(xlsx，格式还原模板)")
def print_form(
    form_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    form = _get_form_or_404(db, form_id)
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
            "name": ap_names.get(a.approver_id, ""),
            "comment": a.comment or "",
            "signature": a.signature_snapshot or "",
            "date": str(a.created_at)[:10] if a.created_at else "",
            "action": a.action.value,
        }

    data = print_svc.build_approval_form_xlsx(
        {
            "form_type": form.form_type,
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
    _: User = Depends(get_current_user),
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
