"""合同端点 —— 【合同(法律)类审批】路径（合同全生命周期 + 逐级审批流）。

⚠️ 审批路径区分（两条流程互不干扰、各自独立）：
- 本模块 `/contracts/*` = **合同(法律)类审批**：合同全生命周期管理，审批操作入口
  内嵌在前端「合同管理」页；审批人在其环节直接「通过/驳回」。
- `/approval`（前端「业务审批」，原审批中心）= **日常业务类审批**，为独立模块，
  当前为存根页，后续单独开发；与本合同审批流无任何共享状态或逻辑。

合同审批链（`APPROVAL_CHAIN`，顺序即流转顺序）：
    业务经办 → 供管公司负责人 → 法律顾问 → 投资公司法务风控 → 投资公司分管领导

流程：
- 业务经办创建草稿并「提交审批」：自动完成第 0 级（附加本人电子签名），
  合同进入 pending，current_step=1（供管公司负责人），进入待审批。
- 后续每一级：仅当前 current_step 对应角色（或超管）可「通过」，
  通过时自动附加本人电子签名快照，随后 current_step+1；走完末级即 approved。
- 任一级可「驳回」（原因必填），合同置为 rejected，全程审批记录留存作审计。
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
    APPROVAL_CHAIN,
    ApprovalAction,
    ContractStatus,
    Role,
    is_final_step,
    role_at_step,
)
from app.db.session import get_db
from app.models.approval import Approval
from app.models.contract import Contract
from app.models.user import User
from app.schemas.approval import ApprovalOut, ApproveRequest, RejectRequest
from app.schemas.common import Response
from app.schemas.contract import ContractCreate, ContractOut, ContractUpdate
from app.services import contract_review as review_svc
from app.services import customer_research as research_svc
from app.services import legal_doc as legal_doc_svc

_OPINION_ROLES = {r for r, _ in legal_doc_svc.OPINION_ROLES}
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter()

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


def _to_out(contract: Contract, creator_name: str = "") -> ContractOut:
    out = ContractOut.model_validate(contract)
    out.creator_name = creator_name
    return out


def _ensure_current_approver(contract: Contract, user: User) -> Role:
    """校验合同处于审批中且当前用户是本级审批人（超管放行）。返回本级期望角色。"""
    if contract.status != ContractStatus.PENDING:
        raise HTTPException(status_code=400, detail="该合同当前不处于审批中，无法操作")
    expected = role_at_step(contract.current_step)
    if expected is None:
        raise HTTPException(status_code=400, detail="审批流状态异常")
    if not user.is_superuser and user.role != expected:
        raise HTTPException(
            status_code=403,
            detail=f"当前审批环节应由【{expected.label}】处理，您无权审批",
        )
    return expected


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #
@router.get("", response_model=Response[list[ContractOut]], summary="合同列表")
def list_contracts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """业务经办仅见本人合同；其余角色（复核/审核/负责人）作为审批与监督方见全部。"""
    stmt = select(Contract).order_by(Contract.id.desc())
    if not current_user.is_superuser and current_user.role == Role.BUSINESS_HANDLER:
        stmt = stmt.where(Contract.created_by == current_user.id)
    rows = db.scalars(stmt).all()
    names = _names_map(db, {c.created_by for c in rows})
    return Response.ok([_to_out(c, names.get(c.created_by, "")) for c in rows])


@router.get("/todo", response_model=Response[list[ContractOut]], summary="待我审批的合同")
def list_todo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """审批中心列表：状态为 pending 且当前环节恰好轮到我处理的合同。"""
    rows = db.scalars(
        select(Contract)
        .where(Contract.status == ContractStatus.PENDING)
        .order_by(Contract.id.desc())
    ).all()
    todo = [
        c for c in rows
        if current_user.is_superuser or role_at_step(c.current_step) == current_user.role
    ]
    names = _names_map(db, {c.created_by for c in todo})
    return Response.ok([_to_out(c, names.get(c.created_by, "")) for c in todo])


@router.get("/{contract_id}", response_model=Response[ContractOut], summary="合同详情")
def get_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    names = _names_map(db, {contract.created_by})
    return Response.ok(_to_out(contract, names.get(contract.created_by, "")))


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
    _get_contract_or_404(db, contract_id)
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
    dependencies=[Depends(require_roles(Role.BUSINESS_HANDLER))],
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
    return Response.ok(_to_out(contract, current_user.full_name))


@router.put(
    "/{contract_id}",
    response_model=Response[ContractOut],
    summary="修改合同(业务经办，仅草稿/驳回态)",
    dependencies=[Depends(require_roles(Role.BUSINESS_HANDLER))],
)
def update_contract(
    contract_id: int,
    payload: ContractUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    if not current_user.is_superuser and contract.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能修改本人创建的合同")
    if contract.status not in (ContractStatus.DRAFT, ContractStatus.REJECTED):
        raise HTTPException(status_code=400, detail="当前状态不可修改")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contract, field, value)
    db.commit()
    db.refresh(contract)
    return Response.ok(_to_out(contract, current_user.full_name))


@router.delete(
    "/{contract_id}",
    response_model=Response[dict],
    summary="删除合同(业务经办，仅草稿/驳回态)",
    dependencies=[Depends(require_roles(Role.BUSINESS_HANDLER))],
)
def delete_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    if not current_user.is_superuser and contract.created_by != current_user.id:
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
    dependencies=[Depends(require_roles(Role.BUSINESS_HANDLER))],
)
def submit_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    if not current_user.is_superuser and contract.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能提交本人创建的合同")
    if contract.status not in (ContractStatus.DRAFT, ContractStatus.REJECTED):
        raise HTTPException(status_code=400, detail="仅草稿或被驳回的合同可提交")

    # 第 0 级（业务经办）随提交自动完成并附加电子签名
    db.add(
        Approval(
            contract_id=contract.id,
            approver_id=current_user.id,
            step=0,
            approver_role=Role.BUSINESS_HANDLER.value,
            action=ApprovalAction.APPROVE,
            comment="提交审批（业务经办）",
            signature_snapshot=current_user.signature,
        )
    )
    contract.status = ContractStatus.PENDING
    contract.current_step = 1  # 流转至业务复核
    db.commit()
    db.refresh(contract)
    return Response.ok(_to_out(contract, current_user.full_name))


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
    _ensure_current_approver(contract, current_user)

    step = contract.current_step
    db.add(
        Approval(
            contract_id=contract.id,
            approver_id=current_user.id,
            step=step,
            approver_role=current_user.role.value,
            action=ApprovalAction.APPROVE,
            comment=payload.comment or "",
            signature_snapshot=current_user.signature,  # 自动电子签章
        )
    )
    if is_final_step(step):
        contract.status = ContractStatus.APPROVED  # 末级通过 → 全流程完成
    else:
        contract.current_step = step + 1
    db.commit()
    db.refresh(contract)
    return Response.ok(_to_out(contract, current_user.full_name))


@router.post(
    "/{contract_id}/reject",
    response_model=Response[ContractOut],
    summary="驳回（原因必填，当前环节角色）",
)
def reject_contract(
    contract_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    _ensure_current_approver(contract, current_user)

    db.add(
        Approval(
            contract_id=contract.id,
            approver_id=current_user.id,
            step=contract.current_step,
            approver_role=current_user.role.value,
            action=ApprovalAction.REJECT,
            comment=payload.comment,
            signature_snapshot=None,
        )
    )
    contract.status = ContractStatus.REJECTED  # 保留 current_step 记录驳回环节
    db.commit()
    db.refresh(contract)
    return Response.ok(_to_out(contract, current_user.full_name))


# --------------------------------------------------------------------------- #
# 合同附件：真实上传 / 下载
# --------------------------------------------------------------------------- #
def _attachment_dir(contract_id: int) -> Path:
    return Path(settings.UPLOAD_DIR) / f"contract_{contract_id}"


@router.post(
    "/{contract_id}/attachment",
    response_model=Response[ContractOut],
    summary="上传合同附件(业务经办，覆盖式单附件)",
    dependencies=[Depends(require_roles(Role.BUSINESS_HANDLER))],
)
async def upload_attachment(
    contract_id: int,
    file: UploadFile = File(..., description="合同附件 PDF/Word/Excel/图片，≤20MB"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    if not current_user.is_superuser and contract.created_by != current_user.id:
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
    return Response.ok(_to_out(contract, names.get(contract.created_by, "")), message="附件上传成功")


@router.get("/{contract_id}/attachment", summary="下载合同附件原件")
def download_attachment(
    contract_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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
@router.get("/{contract_id}/legal-doc", summary="生成并下载法律文件审批表(.docx)")
def download_legal_doc(
    contract_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(db, contract_id)
    creator = _names_map(db, {contract.created_by}).get(contract.created_by, "")

    approvals = db.scalars(
        select(Approval).where(Approval.contract_id == contract_id).order_by(Approval.id.asc())
    ).all()
    ap_names = _names_map(db, {a.approver_id for a in approvals})
    # 每个意见栏取该角色最近一次“通过”的意见 + 签批人 + 日期
    opinions: dict[str, dict] = {}
    for a in approvals:
        if a.approver_role in _OPINION_ROLES and a.action == ApprovalAction.APPROVE:
            opinions[a.approver_role] = {
                "comment": a.comment or "同意",
                "approver_name": ap_names.get(a.approver_id, ""),
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
    _: User = Depends(get_current_user),
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
