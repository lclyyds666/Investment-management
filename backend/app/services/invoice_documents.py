"""Invoice attachment storage and output-detail consistency helpers."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path, PurePath
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.models.invoice import Invoice, InvoiceAttachment

ATTACHMENT_SIGNATURES = {
    ".pdf": b"%PDF-",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
    ".xls": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
}
ATTACHMENT_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".ofd": "application/ofd",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
ALLOWED_EXTENSIONS = frozenset(ATTACHMENT_MIME_TYPES)
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


def _validate_attachment_content(target: Path, extension: str) -> None:
    valid = False
    if extension in {".ofd", ".docx", ".xlsx"}:
        try:
            with ZipFile(target) as archive:
                names = {
                    name.replace("\\", "/").lstrip("/")
                    for name in archive.namelist()
                }
            if extension == ".ofd":
                valid = "OFD.xml" in names
            elif extension == ".docx":
                valid = "[Content_Types].xml" in names and any(
                    name.startswith("word/") for name in names
                )
            else:
                valid = "[Content_Types].xml" in names and any(
                    name.startswith("xl/") for name in names
                )
        except (BadZipFile, OSError):
            valid = False
    else:
        with target.open("rb") as source:
            header = source.read(8)
        valid = header.startswith(ATTACHMENT_SIGNATURES[extension])
    if not valid:
        raise HTTPException(status_code=400, detail="附件内容与文件格式不匹配")


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
        _validate_attachment_content(target, extension)
        attachment = InvoiceAttachment(
            invoice_id=invoice.id,
            original_name=original_name,
            stored_name=stored_name,
            content_type=ATTACHMENT_MIME_TYPES[extension],
            file_size=size,
            uploaded_by=uploaded_by,
        )
        return attachment, target
    except Exception:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
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
