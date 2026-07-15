"""客户档案管理端点（主数据 CRUD + AI 尽职调查）。"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.enums import Role
from app.core.masking import mask_phone
from app.db.session import get_db
from app.models.customer import Customer
from app.models.research import CustomerMaterial, CustomerResearch
from app.models.user import User
from app.schemas.common import Response
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate
from app.services import customer_research as research_svc

router = APIRouter()

# 可维护客户档案的角色
WRITE_ROLES = (Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR)


def _dump_files(payload_dict: dict) -> dict:
    # admission_files 为 pydantic 模型列表，转为可入 JSON 的 dict 列表
    if payload_dict.get("admission_files") is not None:
        payload_dict["admission_files"] = [
            f if isinstance(f, dict) else f.model_dump() for f in payload_dict["admission_files"]
        ]
    return payload_dict


@router.get("", response_model=Response[list[CustomerOut]], summary="客户列表")
def list_customers(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """列表默认对联系电话脱敏（138****5678），明文仅在详情页按需返回。"""
    rows = db.scalars(select(Customer).order_by(Customer.id.desc())).all()
    out = []
    for r in rows:
        item = CustomerOut.model_validate(r)
        item.phone = mask_phone(item.phone)
        out.append(item)
    return Response.ok(out)


@router.get("/{cid}", response_model=Response[CustomerOut], summary="客户详情")
def get_customer(cid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    return Response.ok(CustomerOut.model_validate(c))


@router.post(
    "", response_model=Response[CustomerOut], summary="新建客户",
    dependencies=[Depends(require_roles(*WRITE_ROLES))],
)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Customer).where(Customer.customer_code == payload.customer_code)):
        raise HTTPException(status_code=400, detail="客户ID已存在")
    c = Customer(**_dump_files(payload.model_dump()))
    db.add(c)
    db.commit()
    db.refresh(c)
    return Response.ok(CustomerOut.model_validate(c))


@router.put(
    "/{cid}", response_model=Response[CustomerOut], summary="修改客户",
    dependencies=[Depends(require_roles(*WRITE_ROLES))],
)
def update_customer(cid: int, payload: CustomerUpdate, db: Session = Depends(get_db)):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    for field, value in _dump_files(payload.model_dump(exclude_unset=True)).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return Response.ok(CustomerOut.model_validate(c))


@router.delete(
    "/{cid}", response_model=Response[dict], summary="删除客户",
    dependencies=[Depends(require_roles(*WRITE_ROLES))],
)
def delete_customer(cid: int, db: Session = Depends(get_db)):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    db.delete(c)
    db.commit()
    return Response.ok({"id": cid})


# --------------------------------------------------------------------------- #
# AI 尽职调查：准入资料上传/解析 + 生成调研报告（所有登录用户可用）
# --------------------------------------------------------------------------- #
def _material_out(m: CustomerMaterial) -> dict:
    """列表用摘要，不返回逐页全文（避免体积过大）。"""
    return {
        "id": m.id,
        "filename": m.filename,
        "file_type": m.file_type,
        "page_count": m.page_count,
        "char_count": m.char_count,
        "key_info": m.key_info or {},
        "uploaded_by": m.uploaded_by,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _research_out(r: CustomerResearch) -> dict:
    return {
        "id": r.id,
        "customer_id": r.customer_id,
        "recommendation": r.recommendation,
        "sections": r.sections or {},
        "sources": r.sources or [],
        "report_md": r.report_md,
        "engine": r.engine,
        "searched": r.searched,
        "search_count": r.search_count,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/{cid}/materials", response_model=Response[list[dict]], summary="客户准入资料列表")
def list_materials(cid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(
        select(CustomerMaterial).where(CustomerMaterial.customer_id == cid).order_by(CustomerMaterial.id.desc())
    ).all()
    return Response.ok([_material_out(m) for m in rows])


@router.post("/{cid}/materials", response_model=Response[dict], summary="批量上传并解析准入资料(pdf/docx/xlsx)")
async def upload_materials(
    cid: int,
    files: list[UploadFile] = File(..., description="准入资料，可多选 .pdf / .docx / .xlsx"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量上传即解析：逐个提取文本 + 正则抽取关键信息；原始文件另存磁盘。

    单个文件失败(格式不支持/解析异常)不影响其余文件——收集进 failed 返回，接口不 500。
    返回 {succeeded, failed, warnings, total}。
    """
    if not db.get(Customer, cid):
        raise HTTPException(status_code=404, detail="客户不存在")
    if not files:
        raise HTTPException(status_code=400, detail="未收到任何文件")

    models: list[CustomerMaterial] = []
    failed: list[dict] = []
    warnings: list[str] = []

    for file in files:
        fname = file.filename or "未命名"
        content = await file.read()
        try:
            file_type, pages = research_svc.extract_pages(fname, content)
        except ValueError as exc:
            failed.append({"filename": fname, "reason": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 单文件解析异常不阻断其余
            failed.append({"filename": fname, "reason": f"解析失败：{exc}"})
            continue

        full_text = "\n".join(p["text"] for p in pages)
        key_info = research_svc.extract_key_info(full_text)
        stored_name = research_svc.save_file(cid, fname, content)
        models.append(
            CustomerMaterial(
                customer_id=cid,
                filename=fname,
                stored_name=stored_name,
                file_type=file_type,
                page_count=len(pages),
                char_count=len(full_text),
                pages=pages,
                key_info=key_info,
                uploaded_by=current_user.username,
            )
        )
        if not full_text.strip():
            warnings.append(f"{fname}：未提取到文本，可能为扫描件(图片型)PDF，将无法用于内部资料分析。")

    if models:
        db.add_all(models)
        db.commit()
        for m in models:
            db.refresh(m)

    succeeded = [_material_out(m) for m in models]
    data = {
        "succeeded": succeeded,
        "failed": failed,
        "warnings": warnings,
        "total": len(files),
    }
    if not succeeded:
        # 全部失败：仍返回 200 让前端按 failed 明细提示（符合"接口不 500"约定）
        return Response.ok(data, message="全部文件上传失败，请检查文件格式")
    msg = f"上传并解析成功 {len(succeeded)} 个"
    if failed:
        msg += f"，失败 {len(failed)} 个"
    return Response.ok(data, message=msg)


@router.get("/{cid}/materials/{mid}/download", summary="下载准入资料原件")
def download_material(
    cid: int, mid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    m = db.get(CustomerMaterial, mid)
    if not m or m.customer_id != cid:
        raise HTTPException(status_code=404, detail="资料不存在")
    path = research_svc.file_path(cid, m.stored_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="原始文件已不存在")
    return FileResponse(str(path), filename=m.filename)


@router.delete("/{cid}/materials/{mid}", response_model=Response[dict], summary="删除准入资料")
def delete_material(
    cid: int, mid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    m = db.get(CustomerMaterial, mid)
    if not m or m.customer_id != cid:
        raise HTTPException(status_code=404, detail="资料不存在")
    path = research_svc.file_path(cid, m.stored_name)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass  # 磁盘文件删除失败不阻断记录删除
    db.delete(m)
    db.commit()
    return Response.ok({"id": mid})


@router.get("/{cid}/research", response_model=Response[dict | None], summary="获取最近一次尽调报告")
def get_research(cid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    r = db.scalar(
        select(CustomerResearch).where(CustomerResearch.customer_id == cid).order_by(CustomerResearch.id.desc())
    )
    return Response.ok(_research_out(r) if r else None)


@router.post("/{cid}/research", response_model=Response[dict], summary="生成 AI 尽职调查报告")
def generate_research(cid: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """融合内部准入资料 + 博查外部资讯，经 DeepSeek 综合出四段式尽调报告并标注来源。

    耗时可能 20-60s（解析已在上传时完成，此处为搜索 + 大模型综合）。
    """
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    materials = db.scalars(
        select(CustomerMaterial).where(CustomerMaterial.customer_id == cid)
    ).all()
    if not materials:
        raise HTTPException(status_code=400, detail="请先上传该客户的准入资料再生成报告")

    full_text = "\n\n".join(
        "\n".join(p.get("text", "") for p in (m.pages or [])) for m in materials
    )
    key_info: dict = {}
    for m in materials:  # 合并各资料抽取到的关键信息（后者不覆盖已有非空值）
        for k, v in (m.key_info or {}).items():
            if v and not key_info.get(k):
                key_info[k] = v
    materials_meta = [{"filename": m.filename, "page_count": m.page_count} for m in materials]

    web_results = research_svc.web_search(f"{c.name} 公司 最新 新闻 舆情 诉讼 信用 风险")
    report = research_svc.generate_report(c.name, full_text, key_info, web_results, materials_meta)

    r = CustomerResearch(
        customer_id=cid,
        recommendation=report["recommendation"],
        sections=report["sections"],
        report_md=report["report_md"],
        sources=report["sources"],
        engine=report["engine"],
        searched=report["searched"],
        search_count=report["search_count"],
        created_by=current_user.username,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return Response.ok(_research_out(r), message="尽调报告已生成")
