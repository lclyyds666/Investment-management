"""Invoice attachment storage and output-detail consistency helpers."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path, PurePath
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.models.invoice import Invoice, InvoiceAttachment

ALLOWED_EXTENSIONS = {
    ".pdf", ".ofd", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg",
}
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024


def invoice_upload_root(invoice_id: int) -> Path:
    root = (Path(settings.UPLOAD_DIR) / "invoices" / str(invoice_id)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def invoice_attachment_path(invoice_id: int, stored_name: str) -> Path:
    root = invoice_upload_root(invoice_id)
    if not stored_name or Path(stored_name).name != stored_name:
        raise HTTPException(status_code=400, detail="非法附件路径")
    target = (root / stored_name).resolve()
    if target.parent != root:
        raise HTTPException(status_code=400, detail="非法附件路径")
    return target


def _safe_original_name(filename: str | None) -> str:
    original_name = (filename or "").strip()
    normalized = original_name.replace("\\", "/")
    if not original_name or "/" in normalized or ".." in PurePath(normalized).parts:
        raise HTTPException(status_code=400, detail="非法附件文件名")
    return original_name


async def save_invoice_attachment(
    invoice: Invoice,
    upload: UploadFile,
    *,
    uploaded_by: int | None,
) -> tuple[InvoiceAttachment, Path]:
    original_name = _safe_original_name(upload.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的附件格式")
    stored_name = f"{uuid4().hex}{extension}"
    target = invoice_attachment_path(invoice.id, stored_name)
    size = 0
    try:
        with target.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ATTACHMENT_BYTES:
                    raise HTTPException(status_code=400, detail="附件超过 50MB 上限")
                output.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="附件不能为空")
        attachment = InvoiceAttachment(
            invoice_id=invoice.id,
            original_name=original_name,
            stored_name=stored_name,
            content_type=upload.content_type or "application/octet-stream",
            file_size=size,
            uploaded_by=uploaded_by,
        )
        return attachment, target
    except Exception:
        if target.exists():
            target.unlink()
        raise


def invoice_detail_totals(invoice: Invoice) -> tuple[Decimal, Decimal]:
    total = sum((Decimal(detail.amount) for detail in invoice.details), Decimal("0"))
    return total, Decimal(invoice.amount) - total


def assert_invoice_details_balanced(invoice: Invoice) -> None:
    detail_total, difference = invoice_detail_totals(invoice)
    if difference != Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"发票明细金额不平衡：发票金额 {invoice.amount}，明细合计 {detail_total}，差额 {difference}",
        )
