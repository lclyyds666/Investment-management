"""Invoice management endpoints for source-generated invoices."""
import io
from datetime import date
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import require_permission
from app.core.enums import (
    CompanyCode,
    ContractStatus,
    ContractType,
    InvoiceApprovalStatus,
    InvoiceDirection,
    InvoiceSourceKind,
    InvoiceStatus,
    WorkflowAction,
    WorkflowTargetType,
    WorkflowTaskStatus,
)
from app.db.session import get_db
from app.models.approval_form import ApprovalForm, ApprovalFormAction
from app.models.invoice import Invoice, InvoiceAttachment, InvoiceDetail
from app.models.user import User
from app.models.workflow import WorkflowInstance, WorkflowTask
from app.schemas.approval_form import ApprovalFormOut
from app.schemas.common import Response
from app.schemas.invoice import (
    InvoiceAttachmentOut,
    InvoiceDetailList,
    InvoiceDetailOut,
    InvoiceDetailUpdate,
    InvoiceOut,
    InvoiceRecordStats,
    InvoiceStats,
    InvoiceUpdate,
)
from app.services.assignment_permissions import PermissionContext
from app.services.invoice_documents import (
    assert_invoice_details_balanced,
    invoice_attachment_path,
    invoice_detail_totals,
    save_invoice_attachment,
)
from app.services.invoice_approval_print import (
    build_invoice_approval_docx,
    build_invoice_detail_xlsx,
)
from app.services.num_cn import amount_to_cn
from app.services.workflow_engine import (
    WorkflowTaskConflict,
    WorkflowValidationError,
    complete_task,
    start_workflow,
    task_is_actionable_by,
)

router = APIRouter()

_supply_context = lambda: PermissionContext(company_code=CompanyCode.SUPPLY_MANAGEMENT.value)
_view_guard = require_permission("supply.invoice.view", _supply_context)
_manage_guard = require_permission("supply.invoice.manage", _supply_context)
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _invoice_or_404(db: Session, invoice_id: int, *, with_details: bool = False) -> Invoice:
    if with_details:
        invoice = db.scalar(
            select(Invoice)
            .where(Invoice.id == invoice_id)
            .options(selectinload(Invoice.details))
        )
    else:
        invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="发票不存在")
    return invoice


def _output_invoice_or_409(db: Session, invoice_id: int) -> Invoice:
    invoice = _invoice_or_404(db, invoice_id, with_details=True)
    if invoice.direction != InvoiceDirection.OUTPUT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅销项发票包含核销明细")
    return invoice


def _invoice_form(db: Session, invoice_id: int) -> ApprovalForm | None:
    return db.scalar(
        select(ApprovalForm)
        .where(
            ApprovalForm.invoice_id == invoice_id,
            ApprovalForm.form_type == ContractType.INVOICE,
        )
        .order_by(ApprovalForm.id.desc())
    )


def _active_form_task(db: Session, form: ApprovalForm) -> WorkflowTask | None:
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


def _form_out(db: Session, form: ApprovalForm, current_user: User) -> ApprovalFormOut:
    output = ApprovalFormOut.model_validate(form)
    creator = db.get(User, form.created_by)
    output.creator_name = creator.full_name if creator is not None else ""
    if form.workflow_instance_id is not None:
        instance = db.get(WorkflowInstance, form.workflow_instance_id)
        output.workflow_version = (
            instance.workflow_version.version if instance is not None else None
        )
    task = _active_form_task(db, form)
    if task is not None:
        output.active_task = {
            "id": task.id,
            "node_code": task.node.code,
            "node_name": task.node.name,
            "position_code": task.required_position_code,
            "position_name": task.required_position_name,
        }
        output.can_act = task_is_actionable_by(db, task, current_user)
    return output


def _validate_approval_invoice(invoice: Invoice) -> None:
    if not invoice.customer_name.strip() or not invoice.customer_social_credit_code.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="生成审批单前必须补齐购买方名称和纳税人识别号",
        )
    assert_invoice_details_balanced(invoice)


def _snapshot_invoice_form(
    form: ApprovalForm,
    invoice: Invoice,
    current_user: User,
) -> None:
    form.invoice_id = invoice.id
    form.customer_id = invoice.customer_id
    form.customer_name = invoice.customer_name
    form.business_type = invoice.source_kind.value if invoice.source_kind else ""
    form.business_desc = "业务事项"
    form.contract_no = invoice.contract_no
    form.amount = invoice.amount
    form.amount_words = amount_to_cn(invoice.amount or 0)
    form.bank_name = invoice.customer_bank_name
    form.bank_account = invoice.customer_bank_account
    form.apply_date = date.today()
    form.remark = invoice.remark
    if form.id is None:
        form.created_by = current_user.id


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


@router.get("", response_model=Response[list[InvoiceOut]], summary="发票列表")
def list_invoices(
    direction: InvoiceDirection | None = None,
    scenic_id: str | None = None,
    source_kind: InvoiceSourceKind | None = None,
    period_key: str | None = None,
    invoice_status: InvoiceStatus | None = Query(default=None, alias="status"),
    include_legacy: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    statement = select(Invoice)
    filters = (
        (Invoice.direction, direction),
        (Invoice.scenic_id, scenic_id),
        (Invoice.source_kind, source_kind),
        (Invoice.period_key, period_key),
        (Invoice.status, invoice_status),
    )
    for column, value in filters:
        if value is not None:
            statement = statement.where(column == value)
    if not include_legacy and any(value is not None for _, value in filters[:-1]):
        statement = statement.where(Invoice.generated_by_source.is_(True))
    rows = db.scalars(statement.order_by(Invoice.id.desc())).all()
    return Response.ok([InvoiceOut.model_validate(row) for row in rows])


@router.get("/stats", response_model=Response[InvoiceStats], summary="发票开票统计")
def invoice_stats(db: Session = Depends(get_db), _: User = Depends(_view_guard)):
    rows = db.scalars(select(Invoice)).all()
    issued_amount = sum((row.amount for row in rows if row.status == InvoiceStatus.ISSUED), Decimal("0"))
    pending_amount = sum((row.amount for row in rows if row.status == InvoiceStatus.PENDING), Decimal("0"))
    return Response.ok(InvoiceStats(
        total=len(rows),
        pending=sum(1 for row in rows if row.status == InvoiceStatus.PENDING),
        issued=sum(1 for row in rows if row.status == InvoiceStatus.ISSUED),
        void=sum(1 for row in rows if row.status == InvoiceStatus.VOID),
        issued_amount=issued_amount,
        pending_amount=pending_amount,
    ))


@router.get("/{invoice_id}/stats", response_model=Response[InvoiceRecordStats])
def invoice_record_stats(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    invoice = _invoice_or_404(db, invoice_id, with_details=True)
    detail_total, difference = invoice_detail_totals(invoice)
    attachment_count = len(db.scalars(
        select(InvoiceAttachment.id).where(InvoiceAttachment.invoice_id == invoice_id)
    ).all())
    return Response.ok(InvoiceRecordStats(
        attachment_count=attachment_count,
        detail_count=len(invoice.details),
        detail_total=detail_total,
        difference=difference,
    ))


@router.put("/{invoice_id}", response_model=Response[InvoiceOut], summary="更新发票业务信息")
def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(_manage_guard),
):
    invoice = _invoice_or_404(db, invoice_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(invoice, field, value)
    db.commit()
    db.refresh(invoice)
    return Response.ok(InvoiceOut.model_validate(invoice))


@router.get("/{invoice_id}/attachments", response_model=Response[list[InvoiceAttachmentOut]])
def list_attachments(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    _invoice_or_404(db, invoice_id)
    rows = db.scalars(
        select(InvoiceAttachment)
        .where(InvoiceAttachment.invoice_id == invoice_id)
        .order_by(InvoiceAttachment.id.asc())
    ).all()
    return Response.ok([InvoiceAttachmentOut.model_validate(row) for row in rows])


@router.post("/{invoice_id}/attachments", response_model=Response[list[InvoiceAttachmentOut]])
async def upload_attachments(
    invoice_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_manage_guard),
):
    invoice = _invoice_or_404(db, invoice_id)
    if not files:
        raise HTTPException(status_code=422, detail="至少上传一个附件")
    stored_paths = []
    try:
        for upload in files:
            attachment, path = await save_invoice_attachment(
                invoice, upload, uploaded_by=current_user.id,
            )
            db.add(attachment)
            stored_paths.append(path)
        invoice.status = InvoiceStatus.ISSUED
        db.commit()
    except Exception:
        db.rollback()
        for path in stored_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    rows = db.scalars(
        select(InvoiceAttachment)
        .where(InvoiceAttachment.invoice_id == invoice_id)
        .order_by(InvoiceAttachment.id.asc())
    ).all()
    return Response.ok([InvoiceAttachmentOut.model_validate(row) for row in rows])


@router.get("/{invoice_id}/attachments/{attachment_id}")
def download_attachment(
    invoice_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    _invoice_or_404(db, invoice_id)
    attachment = db.scalar(select(InvoiceAttachment).where(
        InvoiceAttachment.id == attachment_id,
        InvoiceAttachment.invoice_id == invoice_id,
    ))
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = invoice_attachment_path(invoice_id, attachment.stored_name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="附件文件不存在")
    return FileResponse(path, filename=attachment.original_name, media_type=attachment.content_type)


@router.get("/{invoice_id}/details", response_model=Response[InvoiceDetailList])
def list_details(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    invoice = _output_invoice_or_409(db, invoice_id)
    detail_total, difference = invoice_detail_totals(invoice)
    return Response.ok(InvoiceDetailList(
        items=[
            InvoiceDetailOut.model_validate(detail)
            for detail in sorted(invoice.details, key=lambda row: row.line_no)
        ],
        detail_total=detail_total,
        difference=difference,
    ))


@router.put("/{invoice_id}/details/{detail_id}", response_model=Response[InvoiceDetailList])
def update_detail(
    invoice_id: int,
    detail_id: int,
    payload: InvoiceDetailUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(_manage_guard),
):
    invoice = _output_invoice_or_409(db, invoice_id)
    detail = next((row for row in invoice.details if row.id == detail_id), None)
    if detail is None:
        raise HTTPException(status_code=404, detail="发票明细不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(detail, field, value)
    db.commit()
    db.refresh(detail)
    detail_total, difference = invoice_detail_totals(invoice)
    return Response.ok(InvoiceDetailList(
        items=[
            InvoiceDetailOut.model_validate(row)
            for row in sorted(invoice.details, key=lambda row: row.line_no)
        ],
        detail_total=detail_total,
        difference=difference,
    ))


@router.post(
    "/{invoice_id}/approval-form",
    response_model=Response[ApprovalFormOut],
    summary="生成或重新打开销项发票审批单",
)
def create_invoice_approval_form(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_manage_guard),
):
    invoice = _output_invoice_or_409(db, invoice_id)
    _validate_approval_invoice(invoice)
    form = _invoice_form(db, invoice_id)
    if form is not None and form.status in {
        ContractStatus.PENDING,
        ContractStatus.APPROVED,
    }:
        raise HTTPException(status_code=409, detail="当前发票审批单不可重新打开")
    if form is not None and form.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能由原发起人重新打开审批单")
    if form is None:
        form = ApprovalForm(
            form_type=ContractType.INVOICE,
            invoice_id=invoice.id,
            status=ContractStatus.DRAFT,
            current_step=0,
            created_by=current_user.id,
        )
        db.add(form)
    _snapshot_invoice_form(form, invoice, current_user)
    invoice.approval_status = InvoiceApprovalStatus(form.status.value)
    db.commit()
    db.refresh(form)
    return Response.ok(_form_out(db, form, current_user), message="审批单已生成")


@router.post(
    "/{invoice_id}/approval-form/submit",
    response_model=Response[ApprovalFormOut],
    summary="提交销项发票审批单",
)
def submit_invoice_approval_form(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_manage_guard),
):
    invoice = _output_invoice_or_409(db, invoice_id)
    _validate_approval_invoice(invoice)
    form = _invoice_form(db, invoice_id)
    if form is None:
        raise HTTPException(status_code=404, detail="请先生成销项发票审批单")
    if form.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="只能由原发起人提交审批单")
    _snapshot_invoice_form(form, invoice, current_user)
    try:
        if form.workflow_instance_id is None:
            start_workflow(
                db,
                WorkflowTargetType.INVOICE_APPROVAL,
                form.id,
                current_user,
                {},
            )
        else:
            task = _active_form_task(db, form)
            if task is None or not task.node.auto_complete_on_submit:
                raise HTTPException(status_code=422, detail="审批单当前不可重新提交")
            complete_task(
                db,
                task.id,
                current_user,
                WorkflowAction.SUBMIT,
                "重新提交审批",
            )
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
    return Response.ok(_form_out(db, form, current_user), message="已提交审批")


@router.get(
    "/{invoice_id}/approval-form/print",
    summary="打印已通过的销项发票审批单",
)
def print_invoice_approval_form(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    invoice = _output_invoice_or_409(db, invoice_id)
    form = _invoice_form(db, invoice_id)
    if form is None:
        raise HTTPException(status_code=404, detail="销项发票审批单不存在")
    if form.status != ContractStatus.APPROVED:
        raise HTTPException(status_code=409, detail="审批通过后方可打印审批单")
    assert_invoice_details_balanced(invoice)
    actions = list(db.scalars(
        select(ApprovalFormAction)
        .where(ApprovalFormAction.form_id == form.id)
        .order_by(ApprovalFormAction.id)
    ))
    users = {
        user.id: user.full_name
        for user in db.scalars(select(User).where(
            User.id.in_({action.approver_id for action in actions})
        ))
    }
    applicant = next(
        (action for action in actions if action.position_code == "supply.business_reviewer"),
        None,
    )
    approver = next(
        (
            action
            for action in reversed(actions)
            if action.position_code == "governance.supply_leader"
        ),
        None,
    )
    content = build_invoice_approval_docx({
        "customer_name": form.customer_name,
        "tax_no": invoice.customer_social_credit_code,
        "customer_address": invoice.customer_address,
        "customer_phone": invoice.customer_phone,
        "customer_bank_name": form.bank_name,
        "customer_bank_account": form.bank_account,
        "amount": form.amount,
        "contract_no": form.contract_no,
        "business_item": form.business_desc or "业务事项",
        "invoice_type": invoice.invoice_type,
        "applicant_name": users.get(applicant.approver_id, "") if applicant else "",
        "approver_name": users.get(approver.approver_id, "") if approver else "",
        "apply_date": form.apply_date,
        "approval_date": approver.created_at.date() if approver and approver.created_at else None,
        "remark": form.remark,
    })
    filename = quote(f"开票审批单_{form.contract_no or invoice.id}.docx")
    return StreamingResponse(
        io.BytesIO(content),
        media_type=_DOCX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/{invoice_id}/details/print", summary="打印销项开票明细")
def print_invoice_details(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_view_guard),
):
    invoice = _output_invoice_or_409(db, invoice_id)
    assert_invoice_details_balanced(invoice)
    content = build_invoice_detail_xlsx([
        {
            "item_name": detail.item_name,
            "platform": detail.platform,
            "amount": detail.amount,
        }
        for detail in sorted(invoice.details, key=lambda row: row.line_no)
    ])
    filename = quote(f"开票明细_{invoice.period_key or invoice.id}.xlsx")
    return StreamingResponse(
        io.BytesIO(content),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
