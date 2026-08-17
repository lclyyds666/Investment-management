"""投资公司法务风控资源型 API。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.responses import Response as StarletteResponse

from app.api.deps import get_current_user, require_company_resource, require_superuser
from app.core.enums import CompanyCode, ResourceCode
from app.db.session import get_db
from app.models.legal_risk import (
    LegalCase,
    LegalAlertDelivery,
    LegalAlertStatus,
    LegalCaseAlert,
    LegalCaseActivity,
    LegalCaseImportBatch,
    LegalCaseImportRow,
    LegalCaseAsset,
    LegalCaseCollaborator,
    LegalCaseDeadline,
    LegalCaseJudgment,
    LegalCaseParty,
    LegalCaseProgress,
    LegalCaseRecovery,
    LegalCaseStage,
    LegalCaseStatus,
    LegalAttachment,
    LegalCollaboratorType,
    LegalProgressType,
)
from app.models.user import User
from app.schemas.common import Response
from app.schemas.legal_risk import (
    LegalArchiveIn,
    LegalAttachmentOut,
    LegalAssetIn,
    LegalAssetOut,
    LegalCaseCreate,
    LegalCaseDetailOut,
    LegalCaseOut,
    LegalCaseStatusUpdate,
    LegalCaseUpdate,
    LegalCollaboratorIn,
    LegalCollaboratorOut,
    LegalAlertActionIn,
    LegalAlertOut,
    LegalCompletionIn,
    LegalDeadlineIn,
    LegalDeadlineOut,
    LegalJudgmentIn,
    LegalJudgmentOut,
    LegalImportConfirmIn,
    LegalPage,
    LegalPartyIn,
    LegalPartyOut,
    LegalProgressIn,
    LegalProgressOut,
    LegalRecoveryIn,
    LegalRecoveryOut,
    LegalUnarchiveIn,
)
from app.services.legal_cases import (
    activate_case,
    archive_case,
    calculate_case_money,
    change_case_status,
    ensure_version,
    ensure_formal_case_fields,
    ensure_writable,
    get_case_or_403,
    record_activity,
    reserve_case_version,
    set_current_enforcement_basis,
    unarchive_case,
)
from app.services.legal_clock import legal_now, legal_today
from app.services.legal_attachments import (
    INLINE_EXTENSIONS,
    attachment_media_type,
    attachment_path,
    can_delete_attachment,
    save_legal_attachment,
    validate_attachment_relation,
)
from app.services.dingtalk import DingTalkClient
from app.services.legal_alerts import (
    complete_source_alerts,
    dispatch_pending_deliveries,
    ensure_due_deliveries,
    scan_alerts,
    scan_case_alerts,
)
from app.services.legal_permissions import (
    LegalCapability,
    access_context,
    accessible_case_predicate,
    require_legal_capability,
)
from app.services.permissions import get_company_role
from app.services.legal_statistics import (
    LegalCaseFilters,
    dashboard_statistics,
    export_cases_workbook,
    status_statistics,
)
from app.services.legal_imports import (
    build_error_report,
    build_import_template,
    confirm_import,
    preview_import,
)

def _disable_sensitive_response_cache(response: StarletteResponse) -> None:
    response.headers["Cache-Control"] = "no-store"


def _require_route_resource(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    path = request.url.path
    if path.endswith("/statistics/dashboard"):
        resource = ResourceCode.INVEST_LEGAL_DASHBOARD
    elif path.endswith("/statistics/status") or "/exports/" in path:
        resource = ResourceCode.INVEST_LEGAL_STATISTICS
    elif "/alerts" in path:
        resource = ResourceCode.INVEST_LEGAL_ALERTS
    elif "/admin/" in path:
        resource = ResourceCode.INVEST_LEGAL_ADMIN
    else:
        resource = ResourceCode.INVEST_LEGAL_CASES
    return require_company_resource(CompanyCode.INVESTMENT, resource)(
        current_user=current_user,
        db=db,
    )


router = APIRouter(dependencies=[
    Depends(_require_route_resource),
    Depends(_disable_sensitive_response_cache),
])


def _commit(db: Session) -> None:
    case_ids = set(db.info.pop("legal_alert_case_ids", set()))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    for case_id in case_ids:
        _dispatch_case_deliveries(db, case_id)


def _sync_case_alerts(db: Session, case: LegalCase) -> None:
    db.info.setdefault("legal_alert_case_ids", set()).add(case.id)
    today = legal_today()
    for alert in scan_case_alerts(db, case, today):
        ensure_due_deliveries(db, alert, today)


def _pending_case_delivery_ids(db: Session, case_id: int) -> list[int]:
    return list(db.scalars(
        select(LegalAlertDelivery.id)
        .join(LegalCaseAlert, LegalCaseAlert.id == LegalAlertDelivery.alert_id)
        .where(
            LegalCaseAlert.case_id == case_id,
            LegalAlertDelivery.channel == "dingtalk",
            LegalAlertDelivery.status == "pending",
        )
    ).all())


def _dispatch_case_deliveries(db: Session, case_id: int) -> int:
    delivery_ids = _pending_case_delivery_ids(db, case_id)
    if not delivery_ids:
        return 0
    try:
        return dispatch_pending_deliveries(db, delivery_ids=delivery_ids)
    except Exception:
        db.rollback()
        return 0


def _case_out(case: LegalCase) -> LegalCaseOut:
    return LegalCaseOut.model_validate(case)


def _detail_out(db: Session, case: LegalCase) -> LegalCaseDetailOut:
    today = legal_today()
    assets = []
    for row in case.assets:
        if row.deleted_at is not None:
            continue
        data = LegalAssetOut.model_validate(row)
        data.remaining_days = (row.expiry_date - today).days if row.expiry_date else None
        assets.append(data)
    return LegalCaseDetailOut(
        **_case_out(case).model_dump(),
        parties=[LegalPartyOut.model_validate(row) for row in case.parties if row.deleted_at is None],
        collaborators=[LegalCollaboratorOut.model_validate(row) for row in case.collaborators],
        judgments=[LegalJudgmentOut.model_validate(row) for row in case.judgments if row.deleted_at is None],
        assets=assets,
        recoveries=[LegalRecoveryOut.model_validate(row) for row in case.recoveries if row.deleted_at is None],
        progress_records=[LegalProgressOut.model_validate(row) for row in case.progress_records if row.deleted_at is None],
        deadlines=[LegalDeadlineOut.model_validate(row) for row in case.deadlines if row.deleted_at is None],
        money=calculate_case_money(db, case.id),
    )


@router.get("/user-options", response_model=Response[list[dict]], summary="法务案件可选人员")
def legal_user_options(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    users = db.scalars(
        select(User)
        .where(User.is_active.is_(True))
        .order_by(User.full_name.asc(), User.id.asc())
    ).all()
    options = []
    for user in users:
        role = None if user.is_superuser else get_company_role(
            db, user, CompanyCode.INVESTMENT
        )
        if not user.is_superuser and role is None:
            continue
        options.append({
            "id": user.id,
            "name": user.full_name or user.username,
            "role": role.value if role is not None else "superuser",
        })
    return Response.ok(options)


@router.get("/cases", response_model=Response[LegalPage[LegalCaseOut]], summary="案件与草稿列表")
def list_cases(
    keyword: str | None = None,
    stage: LegalCaseStage | None = None,
    status: str | None = None,
    court: str | None = None,
    responsible_user_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = access_context(db, current_user)
    stmt = select(LegalCase).where(
        LegalCase.deleted_at.is_(None),
        accessible_case_predicate(context),
    )
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(
            LegalCase.case_name.like(like),
            LegalCase.case_no.like(like),
            LegalCase.court_case_no.like(like),
        ))
    if stage is not None:
        stmt = stmt.where(LegalCase.stage == stage)
    if status:
        stmt = stmt.where(LegalCase.status == status)
    if court:
        stmt = stmt.where(LegalCase.court.like(f"%{court.strip()}%"))
    if responsible_user_id is not None:
        stmt = stmt.where(LegalCase.responsible_user_id == responsible_user_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(LegalCase.updated_at.desc(), LegalCase.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Response.ok(LegalPage(
        items=[_case_out(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    ))


@router.post("/cases", response_model=Response[LegalCaseOut], summary="新建案件草稿")
def create_case(
    payload: LegalCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.EDIT_CASE)),
):
    case = LegalCase(
        **payload.model_dump(),
        stage=LegalCaseStage.DRAFT,
        status=None,
        created_by=current_user.id,
    )
    db.add(case)
    db.flush()
    record_activity(db, case.id, "create_draft", current_user, summary=case.case_name)
    _commit(db)
    db.refresh(case)
    return Response.ok(_case_out(case), message="草稿已保存")


@router.get("/cases/{case_id}", response_model=Response[LegalCaseDetailOut], summary="案件详情")
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = access_context(db, current_user)
    case = get_case_or_403(db, case_id, context, include_details=True)
    return Response.ok(_detail_out(db, case))


@router.put("/cases/{case_id}", response_model=Response[LegalCaseOut], summary="修改案件基础信息")
def update_case(
    case_id: int,
    payload: LegalCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.EDIT_CASE)),
):
    context = access_context(db, current_user)
    case = get_case_or_403(db, case_id, context)
    ensure_writable(case)
    data = payload.model_dump(exclude_unset=True, exclude={"version"})
    ensure_formal_case_fields(case, data)
    reserve_case_version(db, case, payload.version)
    for field, value in data.items():
        setattr(case, field, value)
    record_activity(db, case.id, "update", current_user, summary="更新案件基础信息")
    _commit(db)
    db.refresh(case)
    return Response.ok(_case_out(case))


@router.delete("/cases/{case_id}", response_model=Response[dict], summary="逻辑删除案件")
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.ARCHIVE_CASE)),
):
    context = access_context(db, current_user)
    case = get_case_or_403(db, case_id, context)
    if case.stage == LegalCaseStage.FORMAL and case.archived_at is None:
        raise HTTPException(status_code=409, detail="正式案件归档后方可删除")
    reserve_case_version(db, case)
    case.deleted_at = legal_now()
    record_activity(db, case.id, "delete", current_user, summary="逻辑删除案件")
    _commit(db)
    return Response.ok({"id": case_id})


@router.post("/cases/{case_id}/activate", response_model=Response[LegalCaseOut], summary="正式建档")
def activate_case_endpoint(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.ACTIVATE_CASE)),
):
    context = access_context(db, current_user)
    case = get_case_or_403(db, case_id, context, include_details=True)
    activate_case(db, case, current_user)
    _sync_case_alerts(db, case)
    _commit(db)
    db.refresh(case)
    return Response.ok(_case_out(case), message="正式建档成功")


@router.post("/cases/{case_id}/status", response_model=Response[LegalCaseOut], summary="变更案件主状态")
def update_case_status(
    case_id: int,
    payload: LegalCaseStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.EDIT_CASE)),
):
    context = access_context(db, current_user)
    case = get_case_or_403(db, case_id, context)
    change_case_status(db, case, payload.status, payload.version, current_user, payload.terminal_date)
    _sync_case_alerts(db, case)
    _commit(db)
    db.refresh(case)
    return Response.ok(_case_out(case))


@router.post("/cases/{case_id}/archive", response_model=Response[LegalCaseOut], summary="归档案件")
def archive_case_endpoint(
    case_id: int,
    payload: LegalArchiveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.ARCHIVE_CASE)),
):
    context = access_context(db, current_user)
    case = get_case_or_403(db, case_id, context)
    archive_case(db, case, payload.note, current_user)
    _commit(db)
    db.refresh(case)
    return Response.ok(_case_out(case))


@router.post("/cases/{case_id}/unarchive", response_model=Response[LegalCaseOut], summary="解除归档")
def unarchive_case_endpoint(
    case_id: int,
    payload: LegalUnarchiveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    context = access_context(db, current_user)
    case = get_case_or_403(db, case_id, context)
    unarchive_case(db, case, payload.reason, current_user)
    _commit(db)
    db.refresh(case)
    return Response.ok(_case_out(case))


def _case_for_detail_write(db: Session, case_id: int, user: User) -> LegalCase:
    context = access_context(db, user)
    case = get_case_or_403(db, case_id, context)
    ensure_writable(case)
    reserve_case_version(db, case)
    return case


@router.post("/cases/{case_id}/parties", response_model=Response[LegalPartyOut])
def create_party(
    case_id: int,
    payload: LegalPartyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = LegalCaseParty(case_id=case.id, **payload.model_dump())
    db.add(row); db.flush()
    record_activity(db, case.id, "create_party", current_user, object_type="party", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalPartyOut.model_validate(row))


@router.put("/cases/{case_id}/parties/{row_id}", response_model=Response[LegalPartyOut])
def update_party(
    case_id: int,
    row_id: int,
    payload: LegalPartyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = db.scalar(select(LegalCaseParty).where(
        LegalCaseParty.id == row_id, LegalCaseParty.case_id == case.id, LegalCaseParty.deleted_at.is_(None)
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="当事人不存在")
    for field, value in payload.model_dump().items(): setattr(row, field, value)
    record_activity(db, case.id, "update_party", current_user, object_type="party", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalPartyOut.model_validate(row))


@router.delete("/cases/{case_id}/parties/{row_id}", response_model=Response[dict])
def delete_party(
    case_id: int,
    row_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = db.scalar(select(LegalCaseParty).where(
        LegalCaseParty.id == row_id, LegalCaseParty.case_id == case.id, LegalCaseParty.deleted_at.is_(None)
    ))
    if row is None: raise HTTPException(status_code=404, detail="当事人不存在")
    row.deleted_at = legal_now()
    record_activity(db, case.id, "delete_party", current_user, object_type="party", object_id=row.id)
    _commit(db)
    return Response.ok({"id": row_id})


@router.post("/cases/{case_id}/collaborators", response_model=Response[LegalCollaboratorOut])
def create_collaborator(
    case_id: int,
    payload: LegalCollaboratorIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    target = db.get(User, payload.user_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=422, detail="协同用户不存在或已停用")
    row = LegalCaseCollaborator(
        case_id=case.id, assigned_by=current_user.id, **payload.model_dump()
    )
    db.add(row); db.flush()
    record_activity(db, case.id, "assign_collaborator", current_user, object_type="collaborator", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalCollaboratorOut.model_validate(row))


@router.delete("/cases/{case_id}/collaborators/{row_id}", response_model=Response[dict])
def delete_collaborator(
    case_id: int,
    row_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = db.scalar(select(LegalCaseCollaborator).where(
        LegalCaseCollaborator.id == row_id, LegalCaseCollaborator.case_id == case.id
    ))
    if row is None: raise HTTPException(status_code=404, detail="协同关系不存在")
    db.delete(row)
    record_activity(db, case.id, "remove_collaborator", current_user, object_type="collaborator", object_id=row_id)
    _commit(db)
    return Response.ok({"id": row_id})


@router.post("/cases/{case_id}/judgments", response_model=Response[LegalJudgmentOut])
def create_judgment(
    case_id: int,
    payload: LegalJudgmentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = LegalCaseJudgment(case_id=case.id, **payload.model_dump())
    db.add(row); db.flush()
    if payload.is_current_enforcement_basis: set_current_enforcement_basis(db, case.id, row.id)
    _sync_case_alerts(db, case)
    record_activity(db, case.id, "create_judgment", current_user, object_type="judgment", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalJudgmentOut.model_validate(row))


@router.put("/cases/{case_id}/judgments/{row_id}", response_model=Response[LegalJudgmentOut])
def update_judgment(
    case_id: int,
    row_id: int,
    payload: LegalJudgmentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = db.scalar(select(LegalCaseJudgment).where(
        LegalCaseJudgment.id == row_id, LegalCaseJudgment.case_id == case.id, LegalCaseJudgment.deleted_at.is_(None)
    ))
    if row is None: raise HTTPException(status_code=404, detail="裁判结果不存在")
    for field, value in payload.model_dump().items(): setattr(row, field, value)
    if payload.is_current_enforcement_basis: set_current_enforcement_basis(db, case.id, row.id)
    _sync_case_alerts(db, case)
    record_activity(db, case.id, "update_judgment", current_user, object_type="judgment", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalJudgmentOut.model_validate(row))


@router.post("/cases/{case_id}/assets", response_model=Response[LegalAssetOut])
def create_asset(
    case_id: int,
    payload: LegalAssetIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = LegalCaseAsset(case_id=case.id, **payload.model_dump())
    db.add(row); db.flush()
    _sync_case_alerts(db, case)
    record_activity(db, case.id, "create_asset", current_user, object_type="asset", object_id=row.id)
    _commit(db); db.refresh(row)
    out = LegalAssetOut.model_validate(row)
    out.remaining_days = (row.expiry_date - legal_today()).days if row.expiry_date else None
    return Response.ok(out)


@router.put("/cases/{case_id}/assets/{row_id}", response_model=Response[LegalAssetOut])
def update_asset(
    case_id: int,
    row_id: int,
    payload: LegalAssetIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = db.scalar(select(LegalCaseAsset).where(
        LegalCaseAsset.id == row_id, LegalCaseAsset.case_id == case.id, LegalCaseAsset.deleted_at.is_(None)
    ))
    if row is None: raise HTTPException(status_code=404, detail="资产记录不存在")
    for field, value in payload.model_dump().items(): setattr(row, field, value)
    _sync_case_alerts(db, case)
    record_activity(db, case.id, "update_asset", current_user, object_type="asset", object_id=row.id)
    _commit(db); db.refresh(row)
    out = LegalAssetOut.model_validate(row)
    out.remaining_days = (row.expiry_date - legal_today()).days if row.expiry_date else None
    return Response.ok(out)


@router.post("/cases/{case_id}/recoveries", response_model=Response[LegalRecoveryOut])
def create_recovery(
    case_id: int,
    payload: LegalRecoveryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = LegalCaseRecovery(case_id=case.id, registered_by=current_user.id, **payload.model_dump())
    db.add(row); db.flush()
    _sync_case_alerts(db, case)
    record_activity(db, case.id, "create_recovery", current_user, object_type="recovery", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalRecoveryOut.model_validate(row))


@router.put("/cases/{case_id}/recoveries/{row_id}", response_model=Response[LegalRecoveryOut])
def update_recovery(
    case_id: int,
    row_id: int,
    payload: LegalRecoveryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = db.scalar(select(LegalCaseRecovery).where(
        LegalCaseRecovery.id == row_id, LegalCaseRecovery.case_id == case.id, LegalCaseRecovery.deleted_at.is_(None)
    ))
    if row is None: raise HTTPException(status_code=404, detail="清回止损记录不存在")
    for field, value in payload.model_dump().items(): setattr(row, field, value)
    _sync_case_alerts(db, case)
    record_activity(db, case.id, "update_recovery", current_user, object_type="recovery", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalRecoveryOut.model_validate(row))


def _can_add_progress(db: Session, user: User, payload: LegalProgressIn) -> None:
    context = access_context(db, user)
    if context.has(LegalCapability.MANAGE_DETAIL): return
    if context.has(LegalCapability.ADD_COUNSEL_CONTENT) and payload.progress_type == LegalProgressType.LEGAL_OPINION:
        return
    raise HTTPException(status_code=403, detail="法律顾问只能新增被指派案件的法律意见")


@router.post("/cases/{case_id}/progress", response_model=Response[LegalProgressOut])
def create_progress(
    case_id: int,
    payload: LegalProgressIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _can_add_progress(db, current_user, payload)
    case = _case_for_detail_write(db, case_id, current_user)
    row = LegalCaseProgress(case_id=case.id, registered_by=current_user.id, **payload.model_dump())
    db.add(row); db.flush()
    record_activity(db, case.id, "create_progress", current_user, object_type="progress", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalProgressOut.model_validate(row))


@router.put("/cases/{case_id}/progress/{row_id}", response_model=Response[LegalProgressOut])
def update_progress(
    case_id: int,
    row_id: int,
    payload: LegalProgressIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _can_add_progress(db, current_user, payload)
    case = _case_for_detail_write(db, case_id, current_user)
    row = db.scalar(select(LegalCaseProgress).where(
        LegalCaseProgress.id == row_id,
        LegalCaseProgress.case_id == case.id,
        LegalCaseProgress.deleted_at.is_(None),
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="进展记录不存在")
    context = access_context(db, current_user)
    if not context.has(LegalCapability.MANAGE_DETAIL) and not (
        context.has(LegalCapability.ADD_COUNSEL_CONTENT)
        and row.registered_by == current_user.id
        and row.progress_type == LegalProgressType.LEGAL_OPINION
    ):
        raise HTTPException(status_code=403, detail="只能修改本人登记的法律意见")
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    record_activity(db, case.id, "update_progress", current_user,
                    object_type="progress", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalProgressOut.model_validate(row))


@router.post("/cases/{case_id}/deadlines", response_model=Response[LegalDeadlineOut])
def create_deadline(
    case_id: int,
    payload: LegalDeadlineIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = LegalCaseDeadline(case_id=case.id, **payload.model_dump())
    db.add(row); db.flush()
    _sync_case_alerts(db, case)
    record_activity(db, case.id, "create_deadline", current_user, object_type="deadline", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalDeadlineOut.model_validate(row))


@router.put("/cases/{case_id}/deadlines/{row_id}", response_model=Response[LegalDeadlineOut])
def update_deadline(
    case_id: int,
    row_id: int,
    payload: LegalDeadlineIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = db.scalar(select(LegalCaseDeadline).where(
        LegalCaseDeadline.id == row_id, LegalCaseDeadline.case_id == case.id, LegalCaseDeadline.deleted_at.is_(None)
    ))
    if row is None: raise HTTPException(status_code=404, detail="期限事件不存在")
    for field, value in payload.model_dump().items(): setattr(row, field, value)
    _sync_case_alerts(db, case)
    record_activity(db, case.id, "update_deadline", current_user, object_type="deadline", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalDeadlineOut.model_validate(row))


@router.post("/cases/{case_id}/deadlines/{row_id}/complete", response_model=Response[LegalDeadlineOut])
def complete_deadline(
    case_id: int,
    row_id: int,
    payload: LegalCompletionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    row = db.scalar(select(LegalCaseDeadline).where(
        LegalCaseDeadline.id == row_id, LegalCaseDeadline.case_id == case.id, LegalCaseDeadline.deleted_at.is_(None)
    ))
    if row is None: raise HTTPException(status_code=404, detail="期限事件不存在")
    row.is_completed = True; row.completed_at = legal_now(); row.completion_note = payload.result
    complete_source_alerts(db, "deadline", row.id, payload.result)
    _sync_case_alerts(db, case)
    record_activity(db, case.id, "complete_deadline", current_user, object_type="deadline", object_id=row.id)
    _commit(db); db.refresh(row)
    return Response.ok(LegalDeadlineOut.model_validate(row))


@router.delete("/cases/{case_id}/{detail_type}/{row_id}", response_model=Response[dict])
def delete_detail(
    case_id: int,
    detail_type: str,
    row_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_DETAIL)),
):
    case = _case_for_detail_write(db, case_id, current_user)
    models = {
        "judgments": LegalCaseJudgment,
        "assets": LegalCaseAsset,
        "recoveries": LegalCaseRecovery,
        "progress": LegalCaseProgress,
        "deadlines": LegalCaseDeadline,
    }
    model = models.get(detail_type)
    if model is None: raise HTTPException(status_code=404, detail="明细类型不存在")
    row = db.scalar(select(model).where(model.id == row_id, model.case_id == case.id, model.deleted_at.is_(None)))
    if row is None: raise HTTPException(status_code=404, detail="明细不存在")
    row.deleted_at = legal_now()
    _sync_case_alerts(db, case)
    record_activity(db, case.id, f"delete_{detail_type}", current_user, object_type=detail_type, object_id=row_id)
    _commit(db)
    return Response.ok({"id": row_id})


@router.get("/cases/{case_id}/activities", response_model=Response[list[dict]], summary="案件操作记录")
def list_activities(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = access_context(db, current_user)
    get_case_or_403(db, case_id, context)
    rows = db.scalars(select(LegalCaseActivity).where(
        LegalCaseActivity.case_id == case_id
    ).order_by(LegalCaseActivity.created_at.desc(), LegalCaseActivity.id.desc())).all()
    return Response.ok([{
        "id": row.id, "action": row.action, "object_type": row.object_type,
        "object_id": row.object_id, "summary": row.change_summary,
        "actor_name": row.actor_name, "created_at": row.created_at.isoformat(),
    } for row in rows])


@router.get("/cases/{case_id}/attachments", response_model=Response[list[LegalAttachmentOut]])
def list_attachments(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = access_context(db, current_user)
    get_case_or_403(db, case_id, context)
    rows = db.scalars(select(LegalAttachment).where(
        LegalAttachment.case_id == case_id,
        LegalAttachment.deleted_at.is_(None),
    ).order_by(LegalAttachment.created_at.desc(), LegalAttachment.id.desc())).all()
    return Response.ok([LegalAttachmentOut.model_validate(row) for row in rows])


@router.post("/attachments", response_model=Response[LegalAttachmentOut], summary="上传法务附件")
async def upload_attachment(
    case_id: int = Form(...),
    related_type: str = Form("case"),
    related_id: int | None = Form(None),
    category: str = Form("other"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.UPLOAD_ATTACHMENT)),
):
    context = access_context(db, current_user)
    case = get_case_or_403(db, case_id, context)
    ensure_writable(case)
    related_type, related_id = validate_attachment_relation(
        db, case_id=case.id, related_type=related_type, related_id=related_id
    )
    reserve_case_version(db, case)
    row, target = await save_legal_attachment(
        db, file, case=case, related_type=related_type, related_id=related_id,
        category=category, actor=current_user,
    )
    record_activity(db, case.id, "upload_attachment", current_user,
                    object_type="attachment", object_id=row.id, summary=row.original_name)
    try:
        _commit(db)
    except Exception:
        if target.exists(): target.unlink()
        raise
    db.refresh(row)
    return Response.ok(LegalAttachmentOut.model_validate(row))


def _attachment_for_user(
    db: Session,
    attachment_id: int,
    current_user: User,
) -> tuple[LegalAttachment, LegalCase]:
    row = db.scalar(select(LegalAttachment).where(
        LegalAttachment.id == attachment_id,
        LegalAttachment.deleted_at.is_(None),
    ))
    if row is None:
        raise HTTPException(status_code=403, detail="无权访问该附件")
    context = access_context(db, current_user)
    case = get_case_or_403(db, row.case_id, context)
    return row, case


@router.get("/attachments/{attachment_id}/preview", summary="鉴权预览附件")
def preview_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row, case = _attachment_for_user(db, attachment_id, current_user)
    if row.extension not in INLINE_EXTENSIONS:
        raise HTTPException(status_code=415, detail="该格式不支持浏览器预览，请下载查看")
    path = attachment_path(row.storage_name)
    if not path.is_file(): raise HTTPException(status_code=404, detail="附件文件缺失")
    record_activity(db, case.id, "preview_attachment", current_user,
                    object_type="attachment", object_id=row.id, summary=row.original_name)
    _commit(db)
    return FileResponse(
        path, media_type=attachment_media_type(row.extension),
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="{row.storage_name}"',
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/attachments/{attachment_id}/download", summary="鉴权下载附件")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row, case = _attachment_for_user(db, attachment_id, current_user)
    path = attachment_path(row.storage_name)
    if not path.is_file(): raise HTTPException(status_code=404, detail="附件文件缺失")
    record_activity(db, case.id, "download_attachment", current_user,
                    object_type="attachment", object_id=row.id, summary=row.original_name)
    _commit(db)
    return FileResponse(
        path, media_type="application/octet-stream", filename=row.original_name,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/attachments/{attachment_id}", response_model=Response[dict], summary="逻辑删除附件")
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row, case = _attachment_for_user(db, attachment_id, current_user)
    context = access_context(db, current_user)
    if not can_delete_attachment(context, row, case):
        raise HTTPException(status_code=403, detail="无权删除该附件")
    reserve_case_version(db, case)
    row.deleted_at = legal_now()
    record_activity(db, case.id, "delete_attachment", current_user,
                    object_type="attachment", object_id=row.id, summary=row.original_name)
    _commit(db)
    return Response.ok({"id": attachment_id})


def _alert_for_user(db: Session, alert_id: int, current_user: User) -> LegalCaseAlert:
    alert = db.get(LegalCaseAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=403, detail="无权访问该预警")
    context = access_context(db, current_user)
    get_case_or_403(db, alert.case_id, context)
    return alert


@router.get("/alerts", response_model=Response[LegalPage[LegalAlertOut]], summary="预警列表")
def list_alerts(
    status: LegalAlertStatus | None = None,
    alert_type: str | None = None,
    level: str | None = None,
    responsible_user_id: int | None = None,
    case_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = access_context(db, current_user)
    stmt = select(LegalCaseAlert).join(LegalCase).where(
        LegalCase.deleted_at.is_(None),
        accessible_case_predicate(context),
    )
    if status is not None: stmt = stmt.where(LegalCaseAlert.status == status)
    if alert_type: stmt = stmt.where(LegalCaseAlert.alert_type == alert_type)
    if level: stmt = stmt.where(LegalCaseAlert.level == level)
    if responsible_user_id is not None:
        stmt = stmt.where(LegalCaseAlert.responsible_user_id == responsible_user_id)
    if case_id is not None: stmt = stmt.where(LegalCaseAlert.case_id == case_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(
        LegalCaseAlert.due_date.asc(), LegalCaseAlert.id.desc()
    ).offset((page - 1) * page_size).limit(page_size)).all()
    return Response.ok(LegalPage(
        items=[LegalAlertOut.model_validate(row) for row in rows],
        total=total, page=page, page_size=page_size,
    ))


@router.get("/alerts/counts", response_model=Response[dict], summary="当前用户预警角标")
def alert_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = access_context(db, current_user)
    rows = db.execute(
        select(LegalCaseAlert.level, func.count())
        .join(LegalCase)
        .where(
            LegalCaseAlert.status.in_([LegalAlertStatus.PENDING, LegalAlertStatus.PROCESSING]),
            LegalCase.deleted_at.is_(None),
            accessible_case_predicate(context),
        )
        .group_by(LegalCaseAlert.level)
    ).all()
    by_level = {level: count for level, count in rows}
    return Response.ok({
        "total": sum(by_level.values()),
        "critical": by_level.get("critical", 0),
        "warning": by_level.get("warning", 0),
    })


@router.get("/alerts/{alert_id}/deliveries", response_model=Response[list[dict]])
def alert_deliveries(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _alert_for_user(db, alert_id, current_user)
    rows = db.scalars(select(LegalAlertDelivery).where(
        LegalAlertDelivery.alert_id == alert_id
    ).order_by(LegalAlertDelivery.id.desc())).all()
    return Response.ok([{
        "id": row.id, "channel": row.channel, "stage_key": row.stage_key,
        "attempts": row.attempts,
        "status": row.status.value if hasattr(row.status, "value") else row.status,
        "response_summary": row.response_summary, "failure_reason": row.failure_reason,
        "last_sent_at": row.last_sent_at.isoformat() if row.last_sent_at else None,
        "next_retry_at": row.next_retry_at.isoformat() if row.next_retry_at else None,
    } for row in rows])


@router.post("/alerts/{alert_id}/start", response_model=Response[LegalAlertOut])
def start_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_ALERT)),
):
    alert = _alert_for_user(db, alert_id, current_user)
    if alert.status != LegalAlertStatus.PENDING:
        raise HTTPException(status_code=409, detail="仅待处理预警可以开始办理")
    alert.status = LegalAlertStatus.PROCESSING
    record_activity(db, alert.case_id, "start_alert", current_user,
                    object_type="alert", object_id=alert.id)
    _commit(db); db.refresh(alert)
    return Response.ok(LegalAlertOut.model_validate(alert))


def _finish_alert(
    db: Session,
    alert: LegalCaseAlert,
    payload: LegalAlertActionIn,
    current_user: User,
    target: LegalAlertStatus,
) -> LegalAlertOut:
    if alert.status not in (LegalAlertStatus.PENDING, LegalAlertStatus.PROCESSING):
        raise HTTPException(status_code=409, detail="预警已完成或关闭")
    alert.status = target
    alert.result = payload.result.strip()
    alert.closed_reason = payload.result.strip() if target == LegalAlertStatus.CLOSED else ""
    alert.completed_at = legal_now()
    record_activity(db, alert.case_id, target.value + "_alert", current_user,
                    object_type="alert", object_id=alert.id, summary=alert.result)
    _commit(db); db.refresh(alert)
    return LegalAlertOut.model_validate(alert)


@router.post("/alerts/{alert_id}/complete", response_model=Response[LegalAlertOut])
def complete_alert(
    alert_id: int,
    payload: LegalAlertActionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_ALERT)),
):
    alert = _alert_for_user(db, alert_id, current_user)
    return Response.ok(_finish_alert(db, alert, payload, current_user, LegalAlertStatus.COMPLETED))


@router.post("/alerts/{alert_id}/close", response_model=Response[LegalAlertOut])
def close_alert(
    alert_id: int,
    payload: LegalAlertActionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.MANAGE_ALERT)),
):
    alert = _alert_for_user(db, alert_id, current_user)
    return Response.ok(_finish_alert(db, alert, payload, current_user, LegalAlertStatus.CLOSED))


@router.post("/alerts/{alert_id}/resend", response_model=Response[dict])
def resend_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    alert = _alert_for_user(db, alert_id, current_user)
    delivery = LegalAlertDelivery(
        alert_id=alert.id, channel="dingtalk",
        stage_key=f"manual-{legal_now().strftime('%Y%m%d%H%M%S%f')}",
        recipient_scope="legal_group", status="pending",
    )
    db.add(delivery); db.flush()
    record_activity(db, alert.case_id, "resend_alert", current_user,
                    object_type="alert", object_id=alert.id)
    _commit(db)
    processed = dispatch_pending_deliveries(db, delivery_ids=[delivery.id])
    db.refresh(delivery)
    return Response.ok({"delivery_id": delivery.id, "status": delivery.status.value, "processed": processed})


@router.post("/admin/scan-alerts", response_model=Response[dict], summary="立即扫描预警")
def admin_scan_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    result = scan_alerts(db)
    _commit(db)
    deliveries_processed = dispatch_pending_deliveries(db)
    return Response.ok({
        "cases_scanned": result.cases_scanned,
        "alerts_created": result.alerts_created,
        "deliveries_created": result.deliveries_created,
        "deliveries_processed": deliveries_processed,
    })


@router.post("/admin/test-dingtalk", response_model=Response[dict], summary="发送钉钉测试消息")
def admin_test_dingtalk(current_user: User = Depends(require_superuser)):
    result = DingTalkClient().send_test(current_user.full_name or current_user.username)
    if not result.success:
        raise HTTPException(status_code=503, detail=result.failure_reason or "钉钉测试发送失败")
    return Response.ok({"status": result.status, "response": result.response_summary})


def _filters(
    keyword: str | None,
    status: LegalCaseStatus | None,
    court: str | None,
    responsible_user_id: int | None,
    subject_amount_min: Decimal | None,
    subject_amount_max: Decimal | None,
    activated_from: date | None,
    activated_to: date | None,
) -> LegalCaseFilters:
    return LegalCaseFilters(
        keyword=keyword, status=status, court=court,
        responsible_user_id=responsible_user_id,
        subject_amount_min=subject_amount_min,
        subject_amount_max=subject_amount_max,
        activated_from=activated_from, activated_to=activated_to,
    )


@router.get("/statistics/dashboard", response_model=Response[dict], summary="法务工作台统计")
def dashboard_statistics_endpoint(
    keyword: str | None = None,
    status: LegalCaseStatus | None = None,
    court: str | None = None,
    responsible_user_id: int | None = None,
    subject_amount_min: Decimal | None = None,
    subject_amount_max: Decimal | None = None,
    activated_from: date | None = None,
    activated_to: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.VIEW_STATISTICS)),
):
    context = access_context(db, current_user)
    return Response.ok(dashboard_statistics(
        db, _filters(keyword, status, court, responsible_user_id, subject_amount_min,
                     subject_amount_max, activated_from, activated_to), context,
    ))


@router.get("/statistics/status", response_model=Response[list[dict]], summary="固定六状态统计")
def status_statistics_endpoint(
    keyword: str | None = None,
    status: LegalCaseStatus | None = None,
    court: str | None = None,
    responsible_user_id: int | None = None,
    subject_amount_min: Decimal | None = None,
    subject_amount_max: Decimal | None = None,
    activated_from: date | None = None,
    activated_to: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.VIEW_STATISTICS)),
):
    context = access_context(db, current_user)
    return Response.ok(status_statistics(
        db, _filters(keyword, status, court, responsible_user_id, subject_amount_min,
                     subject_amount_max, activated_from, activated_to), context,
    ))


@router.get("/exports/cases.xlsx", summary="导出案件管理报表")
def export_cases_endpoint(
    keyword: str | None = None,
    status: LegalCaseStatus | None = None,
    court: str | None = None,
    responsible_user_id: int | None = None,
    subject_amount_min: Decimal | None = None,
    subject_amount_max: Decimal | None = None,
    activated_from: date | None = None,
    activated_to: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = access_context(db, current_user)
    if not (context.has(LegalCapability.IMPORT_EXPORT)
            or context.has(LegalCapability.EXPORT_MANAGEMENT)):
        raise HTTPException(status_code=403, detail="无导出权限")
    buffer = export_cases_workbook(
        db, _filters(keyword, status, court, responsible_user_id, subject_amount_min,
                     subject_amount_max, activated_from, activated_to), context,
        current_user,
    )
    _commit(db)
    filename = quote(f"法务案件_{legal_today().isoformat()}.xlsx")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}", "Cache-Control": "no-store"},
    )


@router.get("/imports/template", summary="下载法务案件标准导入模板")
def import_template(
    _: User = Depends(require_legal_capability(LegalCapability.IMPORT_EXPORT)),
):
    return StreamingResponse(
        build_import_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''legal-case-v1.xlsx", "Cache-Control": "no-store"},
    )


@router.post("/imports/preview", response_model=Response[dict], summary="预检法务案件 Excel")
async def preview_import_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_legal_capability(LegalCapability.IMPORT_EXPORT)),
):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="仅支持标准 .xlsx 模板")
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="导入文件超过 20MB 上限")
    batch = preview_import(db, content, file.filename or "法务案件导入.xlsx", current_user)
    _commit(db); db.refresh(batch)
    return Response.ok({
        "id": batch.id, "status": batch.status.value,
        "total_rows": batch.total_rows, "importable_rows": batch.importable_rows,
        "warning_rows": batch.warning_rows, "error_rows": batch.error_rows,
    })


def _import_batch_for_user(db: Session, batch_id: int, current_user: User) -> LegalCaseImportBatch:
    context = access_context(db, current_user)
    if not context.has(LegalCapability.IMPORT_EXPORT):
        raise HTTPException(status_code=403, detail="无导入权限")
    batch = db.get(LegalCaseImportBatch, batch_id)
    if batch is None or (not current_user.is_superuser and batch.created_by != current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该导入批次")
    return batch


@router.get("/imports/{batch_id}", response_model=Response[dict], summary="导入预检详情")
def get_import_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    batch = _import_batch_for_user(db, batch_id, current_user)
    rows = db.scalars(select(LegalCaseImportRow).where(
        LegalCaseImportRow.batch_id == batch.id
    ).order_by(LegalCaseImportRow.sheet_name, LegalCaseImportRow.row_number)).all()
    return Response.ok({
        "id": batch.id, "file_name": batch.file_name, "status": batch.status.value,
        "total_rows": batch.total_rows, "importable_rows": batch.importable_rows,
        "warning_rows": batch.warning_rows, "error_rows": batch.error_rows,
        "rows": [{
            "id": row.id, "sheet_name": row.sheet_name, "row_number": row.row_number,
            "status": row.validation_status, "warnings": row.warnings, "errors": row.errors,
            "data": row.normalized_data,
        } for row in rows],
    })


@router.post("/imports/{batch_id}/confirm", response_model=Response[dict], summary="确认事务导入")
def confirm_import_endpoint(
    batch_id: int,
    payload: LegalImportConfirmIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    batch = _import_batch_for_user(db, batch_id, current_user)
    try:
        result = confirm_import(db, batch, current_user, payload.confirmed_warning_rows)
        _commit(db)
        return Response.ok(result, message="导入成功")
    except Exception:
        db.rollback()
        raise


@router.get("/imports/{batch_id}/errors.xlsx", summary="下载导入校验报告")
def import_error_report(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    batch = _import_batch_for_user(db, batch_id, current_user)
    rows = db.scalars(select(LegalCaseImportRow).where(
        LegalCaseImportRow.batch_id == batch.id
    ).order_by(LegalCaseImportRow.sheet_name, LegalCaseImportRow.row_number)).all()
    return StreamingResponse(
        build_error_report(rows),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=legal-import-{batch.id}-validation.xlsx", "Cache-Control": "no-store"},
    )
