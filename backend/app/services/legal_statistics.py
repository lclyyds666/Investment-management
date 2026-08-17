"""法务案件共享查询、工作台统计和 Excel 导出。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.legal_risk import (
    LegalAlertStatus,
    LegalCase,
    LegalCaseAlert,
    LegalCaseAsset,
    LegalCaseDeadline,
    LegalCaseStage,
    LegalCaseStatus,
    LegalDeadlineType,
    LegalCaseJudgment,
    LegalCaseRecovery,
    LegalRecoveryType,
)
from app.models.user import User
from app.services.legal_cases import record_activity
from app.services.legal_clock import legal_now_aware, legal_today
from app.services.legal_permissions import LegalAccessContext, accessible_case_predicate


@dataclass(frozen=True)
class LegalCaseFilters:
    keyword: str | None = None
    status: LegalCaseStatus | None = None
    court: str | None = None
    responsible_user_id: int | None = None
    subject_amount_min: Decimal | None = None
    subject_amount_max: Decimal | None = None
    activated_from: date | None = None
    activated_to: date | None = None


STATUS_LABELS = {
    LegalCaseStatus.REVIEW_FILING: "审查立案",
    LegalCaseStatus.IN_TRIAL: "审理中",
    LegalCaseStatus.JUDGED: "已判决",
    LegalCaseStatus.ENFORCEMENT: "执行中",
    LegalCaseStatus.TERMINAL: "终本",
    LegalCaseStatus.CLOSED: "已结案",
}


def excel_safe_text(value: str | None) -> str:
    text = value or ""
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


def build_case_query(filters: LegalCaseFilters, access: LegalAccessContext):
    stmt = select(LegalCase).where(
        LegalCase.stage == LegalCaseStage.FORMAL,
        LegalCase.deleted_at.is_(None),
        accessible_case_predicate(access),
    )
    if filters.keyword:
        like = f"%{filters.keyword.strip()}%"
        stmt = stmt.where(or_(
            LegalCase.case_name.like(like), LegalCase.case_no.like(like),
            LegalCase.court_case_no.like(like),
        ))
    if filters.status is not None: stmt = stmt.where(LegalCase.status == filters.status)
    if filters.court: stmt = stmt.where(LegalCase.court.like(f"%{filters.court.strip()}%"))
    if filters.responsible_user_id is not None:
        stmt = stmt.where(LegalCase.responsible_user_id == filters.responsible_user_id)
    if filters.subject_amount_min is not None:
        stmt = stmt.where(LegalCase.subject_amount >= filters.subject_amount_min)
    if filters.subject_amount_max is not None:
        stmt = stmt.where(LegalCase.subject_amount <= filters.subject_amount_max)
    if filters.activated_from is not None:
        stmt = stmt.where(LegalCase.activated_at >= datetime.combine(filters.activated_from, datetime.min.time()))
    if filters.activated_to is not None:
        stmt = stmt.where(LegalCase.activated_at < datetime.combine(
            filters.activated_to + timedelta(days=1), datetime.min.time()
        ))
    return stmt


def _case_metrics(db: Session, rows: list[LegalCase]) -> dict[int, dict[str, Decimal | int | None]]:
    metrics = {
        case.id: {
            "subject_amount": Decimal(case.subject_amount or 0),
            "recovered_amount": Decimal("0"),
            "avoided_loss_amount": Decimal("0"),
            "executable_amount": None,
            "active_alert_count": 0,
        }
        for case in rows
    }
    case_ids = list(metrics)
    if not case_ids:
        return metrics
    for case_id, executable_amount in db.execute(
        select(LegalCaseJudgment.case_id, LegalCaseJudgment.executable_amount).where(
            LegalCaseJudgment.case_id.in_(case_ids),
            LegalCaseJudgment.is_current_enforcement_basis.is_(True),
            LegalCaseJudgment.deleted_at.is_(None),
        )
    ):
        metrics[case_id]["executable_amount"] = (
            Decimal(executable_amount) if executable_amount is not None else None
        )
    for case_id, recovery_type, amount in db.execute(
        select(
            LegalCaseRecovery.case_id,
            LegalCaseRecovery.recovery_type,
            func.coalesce(func.sum(LegalCaseRecovery.amount), 0),
        ).where(
            LegalCaseRecovery.case_id.in_(case_ids),
            LegalCaseRecovery.deleted_at.is_(None),
        ).group_by(LegalCaseRecovery.case_id, LegalCaseRecovery.recovery_type)
    ):
        key = "recovered_amount" if recovery_type == LegalRecoveryType.RECOVERY else "avoided_loss_amount"
        metrics[case_id][key] = Decimal(amount or 0)
    for case_id, count in db.execute(
        select(LegalCaseAlert.case_id, func.count()).where(
            LegalCaseAlert.case_id.in_(case_ids),
            LegalCaseAlert.status.in_([LegalAlertStatus.PENDING, LegalAlertStatus.PROCESSING]),
        ).group_by(LegalCaseAlert.case_id)
    ):
        metrics[case_id]["active_alert_count"] = count
    for values in metrics.values():
        basis = values["executable_amount"]
        values["outstanding_amount"] = max(
            (basis if basis is not None else values["subject_amount"]) - values["recovered_amount"],
            Decimal("0"),
        )
    return metrics


def _aggregate_rows(rows: list[LegalCase], metrics: dict[int, dict]) -> dict:
    subject_amount = Decimal("0")
    recovered_amount = Decimal("0")
    outstanding_amount = Decimal("0")
    for case in rows:
        values = metrics[case.id]
        subject_amount += values["subject_amount"]
        recovered_amount += values["recovered_amount"]
        outstanding_amount += values["outstanding_amount"]
    alert_count = sum(values["active_alert_count"] for values in (metrics[case.id] for case in rows))
    return {
        "case_count": len(rows),
        "subject_amount": subject_amount,
        "recovered_amount": recovered_amount,
        "outstanding_amount": outstanding_amount,
        "active_alert_count": alert_count,
    }


def status_statistics(db: Session, filters: LegalCaseFilters, access: LegalAccessContext) -> list[dict]:
    rows = db.scalars(build_case_query(filters, access)).all()
    metrics = _case_metrics(db, rows)
    total = len(rows)
    result = []
    for status in LegalCaseStatus:
        selected = [case for case in rows if case.status == status]
        aggregate = _aggregate_rows(selected, metrics)
        aggregate.update({
            "status": status.value,
            "status_label": STATUS_LABELS[status],
            "ratio": Decimal("0") if total == 0 else Decimal(len(selected)) / Decimal(total),
        })
        result.append(aggregate)
    total_row = _aggregate_rows(rows, metrics)
    total_row.update({"status": "total", "status_label": "合计", "ratio": Decimal("0") if total == 0 else Decimal("1")})
    result.append(total_row)
    return result


def dashboard_statistics(db: Session, filters: LegalCaseFilters, access: LegalAccessContext) -> dict:
    rows = db.scalars(build_case_query(filters, access)).all()
    aggregate = _aggregate_rows(rows, _case_metrics(db, rows))
    case_ids = [case.id for case in rows]
    today = legal_today()
    horizon = today + timedelta(days=45)
    upcoming_assets = []
    upcoming_deadlines = []
    upcoming_asset_count = 0
    if case_ids:
        upcoming_asset_count = db.scalar(select(func.count()).select_from(LegalCaseAsset).where(
            LegalCaseAsset.case_id.in_(case_ids), LegalCaseAsset.deleted_at.is_(None),
            LegalCaseAsset.expiry_date.between(today, horizon),
        )) or 0
        upcoming_assets = db.scalars(select(LegalCaseAsset).where(
            LegalCaseAsset.case_id.in_(case_ids), LegalCaseAsset.deleted_at.is_(None),
            LegalCaseAsset.expiry_date.between(today, horizon),
        ).order_by(LegalCaseAsset.expiry_date.asc()).limit(20)).all()
        upcoming_deadlines = db.scalars(select(LegalCaseDeadline).where(
            LegalCaseDeadline.case_id.in_(case_ids), LegalCaseDeadline.deleted_at.is_(None),
            LegalCaseDeadline.is_completed.is_(False),
            LegalCaseDeadline.event_date.between(today, horizon),
        ).order_by(LegalCaseDeadline.event_date.asc()).limit(20)).all()
    aggregate.update({
        "review_filing_count": sum(case.status == LegalCaseStatus.REVIEW_FILING for case in rows),
        "upcoming_asset_count": upcoming_asset_count,
        "upcoming_assets": [{
            "id": row.id, "case_id": row.case_id, "asset_name": row.asset_name,
            "expiry_date": row.expiry_date,
            "remaining_days": (row.expiry_date - today).days,
        } for row in upcoming_assets],
        "upcoming_deadlines": [{
            "id": row.id, "case_id": row.case_id, "title": row.title,
            "deadline_type": row.deadline_type.value, "event_date": row.event_date,
            "remaining_days": (row.event_date - today).days,
        } for row in upcoming_deadlines],
    })
    return aggregate


def export_cases_workbook(
    db: Session,
    filters: LegalCaseFilters,
    access: LegalAccessContext,
    exporter: User,
) -> BytesIO:
    rows = db.scalars(build_case_query(filters, access).order_by(LegalCase.id.asc())).all()
    metrics = _case_metrics(db, rows)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "案件明细"
    sheet.append([
        "案件编号", "案件名称", "法院案号", "案由", "受理法院", "主状态",
        "标的额", "累计回款", "待回款", "立案时间", "归档状态",
    ])
    for case in rows:
        values = metrics[case.id]
        sheet.append([
            excel_safe_text(case.case_no), excel_safe_text(case.case_name),
            excel_safe_text(case.court_case_no), excel_safe_text(case.cause_of_action),
            excel_safe_text(case.court), STATUS_LABELS.get(case.status, ""), float(values["subject_amount"]),
            float(values["recovered_amount"]), float(values["outstanding_amount"]),
            case.activated_at, "已归档" if case.archived_at else "未归档",
        ])
        record_activity(db, case.id, "export", exporter, summary="导出案件管理报表")
    info = workbook.create_sheet("导出说明")
    info.append(["导出人", exporter.full_name or exporter.username])
    info.append(["导出时间", legal_now_aware().isoformat()])
    info.append(["筛选条件", json.dumps(asdict(filters), ensure_ascii=False, default=str)])
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer
