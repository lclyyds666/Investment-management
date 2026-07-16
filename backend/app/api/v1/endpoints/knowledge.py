"""法规知识库端点：上传/列表/删除/下载参考文件（公司合同法、集团制度、法律规范等）。

上传即用 `customer_research.extract_pages` 解析全文入库；AI 合同审查时聚合这些文本作为依据。
权限：列表/下载任意登录用户；上传/删除仅超级管理员（维护基准库）。
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_superuser
from app.core.config import settings
from app.db.session import get_db
from app.models.knowledge import KnowledgeDoc
from app.models.user import User
from app.schemas.common import Response
from app.schemas.knowledge import KnowledgeDocOut
from app.services import customer_research as research_svc

router = APIRouter()

_KB_CATEGORIES = ("公司合同法", "集团企业制度", "法律规范", "其他")


def _kb_dir() -> Path:
    return Path(settings.UPLOAD_DIR) / "knowledge_base"


@router.get("", response_model=Response[list[KnowledgeDocOut]], summary="法规知识库列表")
def list_docs(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(KnowledgeDoc).order_by(KnowledgeDoc.id.desc())).all()
    return Response.ok([KnowledgeDocOut.model_validate(r) for r in rows])


@router.post("", response_model=Response[KnowledgeDocOut], summary="上传法规文件(超管)")
async def upload_doc(
    file: UploadFile = File(..., description="参考文件 .pdf / .docx / .xlsx"),
    title: str = Form(""),
    category: str = Form("法律规范"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    fname = file.filename or "未命名"
    content = await file.read()
    try:
        file_type, pages = research_svc.extract_pages(fname, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"文件解析失败：{exc}")

    text = "\n".join(p.get("text", "") for p in pages).strip()
    if not text:
        raise HTTPException(status_code=400, detail="未能从文件中提取到文本（可能是扫描件或旧 .doc 格式）")

    d = _kb_dir()
    d.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{Path(fname).suffix.lower()}"
    (d / stored).write_bytes(content)

    doc = KnowledgeDoc(
        title=(title.strip() or Path(fname).stem),
        category=category if category in _KB_CATEGORIES else "法律规范",
        filename=fname,
        stored_name=stored,
        file_type=file_type,
        char_count=len(text),
        content=text,
        uploaded_by=current_user.username,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return Response.ok(KnowledgeDocOut.model_validate(doc), message="已加入法规知识库")


@router.delete("/{doc_id}", response_model=Response[dict], summary="删除法规文件(超管)")
def delete_doc(doc_id: int, db: Session = Depends(get_db), _: User = Depends(require_superuser)):
    doc = db.get(KnowledgeDoc, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    if doc.stored_name:
        p = _kb_dir() / doc.stored_name
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass
    db.delete(doc)
    db.commit()
    return Response.ok({"id": doc_id}, message="已删除")


@router.get("/{doc_id}/download", summary="下载法规文件原件")
def download_doc(doc_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = db.get(KnowledgeDoc, doc_id)
    if not doc or not doc.stored_name:
        raise HTTPException(status_code=404, detail="文件不存在")
    p = _kb_dir() / doc.stored_name
    if not p.exists():
        raise HTTPException(status_code=404, detail="文件缺失")
    return FileResponse(str(p), filename=doc.filename or doc.stored_name)
