"""法务案件核心领域服务。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm import Session, selectinload

from app.core.enums import CompanyCode
from app.models.legal_risk import (
    LegalAlertStatus,
    LegalCase,
    LegalCaseActivity,
    LegalCaseAlert,
    LegalCaseParty,
    LegalCaseRecovery,
    LegalCaseSequence,
    LegalCaseStage,
    LegalCaseStatus,
    LegalCaseJudgment,
    LegalJudgmentType,
    LegalPartyType,
    LegalRecoveryType,
)
from app.models.portal import UserCompanyRole
from app.models.user import User
from app.schemas.legal_risk import LegalMoneySummary
from app.services.legal_clock import legal_now, legal_today
from app.services.legal_permissions import LegalAccessContext, can_access_case


CASE_DETAIL_OPTIONS = (
    selectinload(LegalCase.parties),
    selectinload(LegalCase.collaborators),
    selectinload(LegalCase.judgments),
    selectinload(LegalCase.assets),
    selectinload(LegalCase.recoveries),
    selectinload(LegalCase.progress_records),
    selectinload(LegalCase.deadlines),
)


def resolve_investment_user_name(db: Session, name: str) -> User:
    normalized = name.strip()
    rows = db.scalars(
        select(User)
        .join(UserCompanyRole, UserCompanyRole.user_id == User.id)
        .where(
            or_(
                User.full_name == normalized,
                and_(User.full_name == "", User.username == normalized),
            ),
            User.is_active.is_(True),
            UserCompanyRole.company_code == CompanyCode.INVESTMENT.value,
        )
        .order_by(User.id.asc())
    ).all()
    if not rows:
        raise HTTPException(status_code=422, detail="未找到姓名对应的启用投资公司账号")
    if len(rows) > 1:
        raise HTTPException(status_code=422, detail="该姓名对应多个账号，请先确保账号姓名唯一")
    return rows[0]


def get_case_or_403(
    db: Session,
    case_id: int,
    context: LegalAccessContext,
    *,
    include_details: bool = False,
) -> LegalCase:
    if include_details:
        case = db.scalar(
            select(LegalCase).options(*CASE_DETAIL_OPTIONS).where(
                LegalCase.id == case_id,
                LegalCase.deleted_at.is_(None),
            )
        )
    else:
        case = db.scalar(
            select(LegalCase).where(LegalCase.id == case_id, LegalCase.deleted_at.is_(None))
        )
    if case is None or not can_access_case(db, case, context):
        raise HTTPException(status_code=404, detail="案件不存在")
    return case


def ensure_writable(case: LegalCase) -> None:
    if case.archived_at is not None:
        raise HTTPException(status_code=409, detail="案件已归档，不能修改")


def ensure_version(case: LegalCase, expected_version: int) -> None:
    if case.version != expected_version:
        raise HTTPException(status_code=409, detail="案件已被其他用户修改，请刷新后重试")


def reserve_case_version(db: Session, case: LegalCase, expected_version: int | None = None) -> int:
    expected = case.version if expected_version is None else expected_version
    result = db.execute(
        update(LegalCase)
        .where(
            LegalCase.id == case.id,
            LegalCase.version == expected,
            LegalCase.deleted_at.is_(None),
        )
        .values(version=expected + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="案件已被其他用户修改，请刷新后重试")
    set_committed_value(case, "version", expected + 1)
    return expected + 1


def ensure_formal_case_fields(case: LegalCase, overrides: dict | None = None) -> None:
    if case.stage != LegalCaseStage.FORMAL:
        return
    values = overrides or {}
    required = {
        "案件名称": values.get("case_name", case.case_name),
        "案由": values.get("cause_of_action", case.cause_of_action),
        "受理法院": values.get("court", case.court),
        "法院案号": values.get("court_case_no", case.court_case_no),
        "负责人": values.get("responsible_user_id", case.responsible_user_id),
    }
    missing = [label for label, value in required.items() if not value]
    if values.get("subject_amount", case.subject_amount) is None:
        missing.append("标的额")
    if missing:
        raise HTTPException(status_code=422, detail=f"正式案件必填字段不能清空：{'、'.join(missing)}")


def record_activity(
    db: Session,
    case_id: int,
    action: str,
    actor: User,
    *,
    object_type: str = "case",
    object_id: int | None = None,
    summary: str = "",
) -> None:
    db.add(LegalCaseActivity(
        case_id=case_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        change_summary=summary,
        actor_id=actor.id,
        actor_name=actor.full_name or actor.username,
    ))


def next_case_no(db: Session, year: int) -> str:
    sequence = db.scalar(
        select(LegalCaseSequence).where(LegalCaseSequence.year == year).with_for_update()
    )
    if sequence is None:
        sequence = LegalCaseSequence(year=year, current_value=0)
        db.add(sequence)
        db.flush()
    sequence.current_value += 1
    db.flush()
    return f"AJ-{year}-{sequence.current_value:04d}"


def activate_case(db: Session, case: LegalCase, actor: User) -> LegalCase:
    ensure_writable(case)
    if case.stage != LegalCaseStage.DRAFT:
        raise HTTPException(status_code=409, detail="案件已正式建档，不能重复操作")
    required = {
        "案件名称": case.case_name,
        "案由": case.cause_of_action,
        "受理法院": case.court,
        "法院案号": case.court_case_no,
        "负责人": case.responsible_user_id,
    }
    missing = [label for label, value in required.items() if not value]
    if case.subject_amount is None:
        missing.append("标的额")
    active_parties = [party for party in case.parties if party.deleted_at is None]
    if not any(p.party_type == LegalPartyType.PLAINTIFF for p in active_parties):
        missing.append("原告")
    if not any(p.party_type == LegalPartyType.DEFENDANT for p in active_parties):
        missing.append("被告")
    if missing:
        raise HTTPException(status_code=422, detail=f"正式建档缺少：{'、'.join(missing)}")

    reserve_case_version(db, case)
    now = legal_now()
    case.case_no = next_case_no(db, now.year)
    case.stage = LegalCaseStage.FORMAL
    case.status = LegalCaseStatus.REVIEW_FILING
    case.activated_by = actor.id
    case.activated_at = now
    record_activity(db, case.id, "activate", actor, summary=f"正式建档：{case.case_no}")
    db.flush()
    return case


def change_case_status(
    db: Session,
    case: LegalCase,
    new_status: LegalCaseStatus,
    expected_version: int,
    actor: User,
    terminal_date: date | None = None,
) -> LegalCase:
    ensure_writable(case)
    reserve_case_version(db, case, expected_version)
    if case.stage != LegalCaseStage.FORMAL:
        raise HTTPException(status_code=409, detail="草稿不能变更案件主状态")
    old = case.status
    case.status = new_status
    case.terminal_date = terminal_date or legal_today() if new_status == LegalCaseStatus.TERMINAL else None
    if new_status != LegalCaseStatus.CLOSED:
        case.closed_date = None
        case.closure_summary = ""
    record_activity(db, case.id, "status_change", actor, summary=f"{old.value if old else ''} -> {new_status.value}")
    db.flush()
    return case


def archive_case(db: Session, case: LegalCase, note: str, actor: User) -> LegalCase:
    ensure_writable(case)
    if case.status != LegalCaseStatus.CLOSED:
        raise HTTPException(status_code=409, detail="仅已结案案件可以归档")
    if not case.closed_date or not case.closure_summary.strip():
        raise HTTPException(status_code=409, detail="归档前必须填写结案日期和结案结果摘要")
    active_alerts = db.scalar(
        select(func.count()).select_from(LegalCaseAlert).where(
            LegalCaseAlert.case_id == case.id,
            LegalCaseAlert.status.in_([LegalAlertStatus.PENDING, LegalAlertStatus.PROCESSING]),
        )
    ) or 0
    if active_alerts:
        raise HTTPException(status_code=409, detail="仍有未处理预警，不能归档")
    reserve_case_version(db, case)
    case.archived_at = legal_now()
    case.archive_note = note.strip()
    record_activity(db, case.id, "archive", actor, summary=case.archive_note)
    db.flush()
    return case


def unarchive_case(db: Session, case: LegalCase, reason: str, actor: User) -> LegalCase:
    if case.archived_at is None:
        raise HTTPException(status_code=409, detail="案件尚未归档")
    reserve_case_version(db, case)
    case.archived_at = None
    case.archive_note = ""
    record_activity(db, case.id, "unarchive", actor, summary=reason.strip())
    db.flush()
    return case


def set_current_enforcement_basis(
    db: Session,
    case_id: int,
    judgment_id: int | None,
) -> None:
    rows = db.scalars(
        select(LegalCaseJudgment).where(
            LegalCaseJudgment.case_id == case_id,
            LegalCaseJudgment.deleted_at.is_(None),
        )
    ).all()
    found = judgment_id is None
    for row in rows:
        row.is_current_enforcement_basis = row.id == judgment_id
        found = found or row.id == judgment_id
    if not found:
        raise HTTPException(status_code=404, detail="裁判结果不存在")
    db.flush()


def calculate_case_money(db: Session, case_id: int) -> LegalMoneySummary:
    case = db.get(LegalCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="案件不存在")
    basis = db.scalar(
        select(LegalCaseJudgment).where(
            LegalCaseJudgment.case_id == case_id,
            LegalCaseJudgment.is_current_enforcement_basis.is_(True),
            LegalCaseJudgment.deleted_at.is_(None),
        ).limit(1)
    )
    recovered = db.scalar(
        select(func.coalesce(func.sum(LegalCaseRecovery.amount), 0)).where(
            LegalCaseRecovery.case_id == case_id,
            LegalCaseRecovery.recovery_type == LegalRecoveryType.RECOVERY,
            LegalCaseRecovery.deleted_at.is_(None),
        )
    ) or Decimal("0")
    avoided = db.scalar(
        select(func.coalesce(func.sum(LegalCaseRecovery.amount), 0)).where(
            LegalCaseRecovery.case_id == case_id,
            LegalCaseRecovery.recovery_type == LegalRecoveryType.AVOIDED_LOSS,
            LegalCaseRecovery.deleted_at.is_(None),
        )
    ) or Decimal("0")
    subject = Decimal(case.subject_amount or 0)
    executable = Decimal(basis.executable_amount) if basis and basis.executable_amount is not None else None
    outstanding = max((executable or Decimal("0")) - Decimal(recovered), Decimal("0"))
    return LegalMoneySummary(
        subject_amount=subject,
        executable_amount=executable,
        recovered_amount=Decimal(recovered),
        avoided_loss_amount=Decimal(avoided),
        outstanding_amount=outstanding,
    )
