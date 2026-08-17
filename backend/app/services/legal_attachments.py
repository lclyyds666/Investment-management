"""法务附件安全存储和对象级权限。"""
from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.legal_risk import (
    LegalAttachment,
    LegalCase,
    LegalCaseAsset,
    LegalCaseDeadline,
    LegalCaseJudgment,
    LegalCaseParty,
    LegalCaseProgress,
    LegalCaseRecovery,
)
from app.models.user import User
from app.services.legal_permissions import LegalAccessContext, LegalCapability

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"}
INLINE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
ATTACHMENT_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
RELATED_MODELS = {
    "party": LegalCaseParty,
    "judgment": LegalCaseJudgment,
    "asset": LegalCaseAsset,
    "recovery": LegalCaseRecovery,
    "progress": LegalCaseProgress,
    "deadline": LegalCaseDeadline,
}


def legal_upload_root() -> Path:
    root = Path(settings.UPLOAD_DIR) / "legal-risk"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def attachment_path(storage_name: str) -> Path:
    root = legal_upload_root()
    target = (root / Path(storage_name).name).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=400, detail="非法文件路径")
    return target


def attachment_media_type(extension: str) -> str:
    return ATTACHMENT_MIME_TYPES.get(extension.lower(), "application/octet-stream")


def _valid_office_zip(target: Path, expected_root: str) -> bool:
    try:
        with ZipFile(target) as archive:
            names = set(archive.namelist())
        return "[Content_Types].xml" in names and any(
            name.startswith(f"{expected_root}/") for name in names
        )
    except (BadZipFile, OSError):
        return False


def validate_attachment_content(target: Path, extension: str) -> None:
    with target.open("rb") as source:
        header = source.read(16)
    valid = False
    if extension == ".pdf":
        valid = header.startswith(b"%PDF-")
    elif extension == ".png":
        valid = header.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in {".jpg", ".jpeg"}:
        valid = header.startswith(b"\xff\xd8\xff")
    elif extension in {".doc", ".xls"}:
        valid = header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    elif extension == ".docx":
        valid = header.startswith(b"PK") and _valid_office_zip(target, "word")
    elif extension == ".xlsx":
        valid = header.startswith(b"PK") and _valid_office_zip(target, "xl")
    if not valid:
        raise HTTPException(status_code=400, detail="附件内容与文件格式不匹配")


def validate_attachment_relation(
    db: Session,
    *,
    case_id: int,
    related_type: str,
    related_id: int | None,
) -> tuple[str, int | None]:
    normalized_type = related_type.strip().lower() or "case"
    if normalized_type == "case":
        if related_id not in (None, case_id):
            raise HTTPException(status_code=422, detail="案件附件关联对象无效")
        return normalized_type, None
    model = RELATED_MODELS.get(normalized_type)
    if model is None or related_id is None:
        raise HTTPException(status_code=422, detail="附件关联对象类型或编号无效")
    exists = db.scalar(select(model.id).where(
        model.id == related_id,
        model.case_id == case_id,
        model.deleted_at.is_(None),
    ))
    if exists is None:
        raise HTTPException(status_code=422, detail="附件关联对象不属于当前案件")
    return normalized_type, related_id


async def save_legal_attachment(
    db: Session,
    upload: UploadFile,
    *,
    case: LegalCase,
    related_type: str,
    related_id: int | None,
    category: str,
    actor: User,
) -> tuple[LegalAttachment, Path]:
    original_name = Path(upload.filename or "附件").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的附件格式")
    storage_name = f"{uuid4().hex}{suffix}"
    target = attachment_path(storage_name)
    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ATTACHMENT_BYTES:
                    raise HTTPException(status_code=400, detail="附件超过 50MB 上限")
                digest.update(chunk)
                output.write(chunk)
        validate_attachment_content(target, suffix)
        row = LegalAttachment(
            case_id=case.id,
            related_type=related_type,
            related_id=related_id,
            category=category.strip() or "other",
            original_name=original_name,
            storage_name=storage_name,
            extension=suffix,
            mime_type=attachment_media_type(suffix),
            size_bytes=size,
            sha256=digest.hexdigest(),
            uploaded_by=actor.id,
        )
        db.add(row)
        db.flush()
        return row, target
    except Exception:
        if target.exists():
            target.unlink()
        raise


def can_delete_attachment(
    context: LegalAccessContext,
    attachment: LegalAttachment,
    case: LegalCase,
) -> bool:
    if case.archived_at is not None:
        return False
    if context.has(LegalCapability.MANAGE_DETAIL):
        return True
    return (
        context.has(LegalCapability.DELETE_ATTACHMENT)
        and attachment.uploaded_by == context.user_id
    )
