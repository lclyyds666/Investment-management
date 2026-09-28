"""Invoice management endpoints for source-generated invoices."""
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.enums import CompanyCode, InvoiceDirection, InvoiceSourceKind, InvoiceStatus
from app.db.session import get_db
from app.models.invoice import Invoice, InvoiceAttachment, InvoiceDetail
from app.models.user import User
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
    invoice_attachment_path,
    invoice_detail_totals,
    save_invoice_attachment,
)

router = APIRouter()

_supply_context = lambda: PermissionContext(company_code=CompanyCode.SUPPLY_MANAGEMENT.value)
_view_guard = require_permission("supply.invoice.view", _supply_context)
_manage_guard = require_permission("supply.invoice.manage", _supply_context)


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
