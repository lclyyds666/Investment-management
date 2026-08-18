"""法务五类预警生成、投递阶段与补偿。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.legal_risk import (
    LegalAlertDelivery,
    LegalAlertStatus,
    LegalAlertType,
    LegalCase,
    LegalCaseAlert,
    LegalCaseAsset,
    LegalCaseDeadline,
    LegalCaseJudgment,
    LegalCaseStage,
    LegalCaseStatus,
    LegalDeadlineType,
    LegalDeliveryStatus,
)
from app.models.user import User
from app.services.dingtalk import DingTalkClient
from app.services.legal_cases import calculate_case_money
from app.services.legal_clock import legal_now, legal_today

ACTIVE_ALERT_STATUSES = (LegalAlertStatus.PENDING, LegalAlertStatus.PROCESSING)
RETRY_DELAYS = (timedelta(minutes=5), timedelta(minutes=30), timedelta(minutes=120))
DELIVERY_CLAIM_LEASE = timedelta(minutes=5)


@dataclass(frozen=True)
class AlertScanResult:
    cases_scanned: int
    alerts_created: int
    deliveries_created: int


def _level(due_date: date, today: date) -> str:
    days = (due_date - today).days
    if days < 0: return "critical"
    if days <= 7: return "warning"
    return "normal"


def _deadline_alert_rule(deadline_type: LegalDeadlineType) -> tuple[LegalAlertType, int]:
    if deadline_type == LegalDeadlineType.HEARING:
        return LegalAlertType.HEARING, 45
    if deadline_type == LegalDeadlineType.PAYMENT_MATERIAL:
        return LegalAlertType.PAYMENT_MATERIAL, 7
    return LegalAlertType.CUSTOM, 7


def _ensure_alert(
    db: Session,
    *,
    case: LegalCase,
    source_type: str,
    source_id: int,
    alert_type: LegalAlertType,
    cycle_key: str,
    trigger_date: date,
    due_date: date,
    responsible_user_id: int | None,
    today: date,
    allow_new_generation: bool = False,
) -> tuple[LegalCaseAlert, bool]:
    old_rows = db.scalars(select(LegalCaseAlert).where(
        LegalCaseAlert.case_id == case.id,
        LegalCaseAlert.source_type == source_type,
        LegalCaseAlert.source_id == source_id,
        or_(
            LegalCaseAlert.alert_type != alert_type,
            LegalCaseAlert.cycle_key != cycle_key,
        ),
        LegalCaseAlert.status.in_(ACTIVE_ALERT_STATUSES),
    )).all()
    for old in old_rows:
        old.status = LegalAlertStatus.CLOSED
        old.result = "来源日期已变更"
        old.closed_reason = "来源日期已变更"
        old.completed_at = legal_now()

    matching = db.scalars(select(LegalCaseAlert).where(
        LegalCaseAlert.case_id == case.id,
        LegalCaseAlert.source_type == source_type,
        LegalCaseAlert.source_id == source_id,
        LegalCaseAlert.alert_type == alert_type,
        LegalCaseAlert.cycle_key == cycle_key,
    ).order_by(LegalCaseAlert.generation.desc())).all()
    existing = next((row for row in matching if row.status in ACTIVE_ALERT_STATUSES), None)
    if existing is not None:
        existing.trigger_date = trigger_date
        existing.due_date = due_date
        existing.responsible_user_id = responsible_user_id
        existing.level = _level(due_date, today)
        return existing, False
    if matching and not allow_new_generation:
        return matching[0], False
    generation = matching[0].generation + 1 if matching else 1
    row = LegalCaseAlert(
        case_id=case.id,
        source_type=source_type,
        source_id=source_id,
        alert_type=alert_type,
        cycle_key=cycle_key,
        generation=generation,
        trigger_date=trigger_date,
        due_date=due_date,
        level=_level(due_date, today),
        responsible_user_id=responsible_user_id,
        status=LegalAlertStatus.PENDING,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = db.scalar(select(LegalCaseAlert).where(
            LegalCaseAlert.case_id == case.id,
            LegalCaseAlert.source_type == source_type,
            LegalCaseAlert.source_id == source_id,
            LegalCaseAlert.alert_type == alert_type,
            LegalCaseAlert.cycle_key == cycle_key,
            LegalCaseAlert.generation == generation,
        ).with_for_update())
        if existing is None:
            raise
        existing.trigger_date = trigger_date
        existing.due_date = due_date
        existing.responsible_user_id = responsible_user_id
        existing.level = _level(due_date, today)
        return existing, False
    return row, True


def scan_case_alerts(db: Session, case: LegalCase, today: date) -> list[LegalCaseAlert]:
    if case.stage != LegalCaseStage.FORMAL or case.deleted_at is not None or case.archived_at is not None:
        return []
    active_sources = {}
    for asset in case.assets:
        if asset.deleted_at is None and asset.expiry_date is not None:
            active_sources[("asset", asset.id)] = (
                LegalAlertType.ASSET_EXPIRY,
                asset.expiry_date.isoformat(),
            )
    outstanding = calculate_case_money(db, case.id).outstanding_amount
    for judgment in case.judgments:
        if (judgment.deleted_at is None and judgment.is_current_enforcement_basis
                and judgment.performance_deadline is not None and outstanding > 0):
            active_sources[("judgment", judgment.id)] = (
                LegalAlertType.ENFORCEMENT_APPLICATION,
                judgment.performance_deadline.isoformat(),
            )
    for deadline in case.deadlines:
        if deadline.deleted_at is None and not deadline.is_completed:
            alert_type, _ = _deadline_alert_rule(deadline.deadline_type)
            active_sources[("deadline", deadline.id)] = (
                alert_type,
                deadline.event_date.isoformat(),
            )
    if case.status == LegalCaseStatus.TERMINAL:
        active_sources[("case", case.id)] = (
            LegalAlertType.TERMINAL_MONITORING,
            f"{today.year:04d}-{today.month:02d}",
        )
    source_alerts = db.scalars(select(LegalCaseAlert).where(
        LegalCaseAlert.case_id == case.id,
    ).order_by(LegalCaseAlert.id.desc())).all()
    latest_by_source = {}
    for alert in source_alerts:
        latest_by_source.setdefault((alert.source_type, alert.source_id), alert)

    changed_sources = {
        source
        for source, expected in active_sources.items()
        if source in latest_by_source
        and (latest_by_source[source].alert_type, latest_by_source[source].cycle_key) != expected
    }
    existing_alerts = [
        alert for alert in source_alerts if alert.status in ACTIVE_ALERT_STATUSES
    ]
    for alert in existing_alerts:
        expected_source = active_sources.get((alert.source_type, alert.source_id))
        if expected_source != (alert.alert_type, alert.cycle_key):
            alert.status = LegalAlertStatus.CLOSED
            alert.result = "来源日期已变更或事项已完成"
            alert.closed_reason = alert.result
            alert.completed_at = legal_now()

    generated: list[LegalCaseAlert] = []
    for asset in case.assets:
        if asset.deleted_at is not None or asset.expiry_date is None: continue
        days = asset.reminder_days if asset.reminder_days is not None else 45
        trigger = asset.expiry_date - timedelta(days=days)
        if today >= trigger:
            row, _ = _ensure_alert(
                db, case=case, source_type="asset", source_id=asset.id,
                alert_type=LegalAlertType.ASSET_EXPIRY, cycle_key=asset.expiry_date.isoformat(),
                trigger_date=trigger, due_date=asset.expiry_date,
                responsible_user_id=case.responsible_user_id, today=today,
                allow_new_generation=("asset", asset.id) in changed_sources,
            )
            generated.append(row)

    for judgment in case.judgments:
        if (judgment.deleted_at is not None or not judgment.is_current_enforcement_basis
                or judgment.performance_deadline is None):
            continue
        if today >= judgment.performance_deadline and calculate_case_money(db, case.id).outstanding_amount > 0:
            row, _ = _ensure_alert(
                db, case=case, source_type="judgment", source_id=judgment.id,
                alert_type=LegalAlertType.ENFORCEMENT_APPLICATION,
                cycle_key=judgment.performance_deadline.isoformat(),
                trigger_date=judgment.performance_deadline, due_date=judgment.performance_deadline,
                responsible_user_id=case.responsible_user_id, today=today,
                allow_new_generation=("judgment", judgment.id) in changed_sources,
            )
            generated.append(row)

    for deadline in case.deadlines:
        if deadline.deleted_at is not None or deadline.is_completed: continue
        alert_type, default_days = _deadline_alert_rule(deadline.deadline_type)
        days = deadline.reminder_days if deadline.reminder_days is not None else default_days
        trigger = deadline.event_date - timedelta(days=days)
        row, _ = _ensure_alert(
            db, case=case, source_type="deadline", source_id=deadline.id,
            alert_type=alert_type, cycle_key=deadline.event_date.isoformat(),
            trigger_date=trigger, due_date=deadline.event_date,
            responsible_user_id=deadline.responsible_user_id or case.responsible_user_id,
            today=today,
            allow_new_generation=("deadline", deadline.id) in changed_sources,
        )
        generated.append(row)

    if case.status == LegalCaseStatus.TERMINAL:
        month_start = today.replace(day=1)
        trigger = max(case.terminal_date or month_start, month_start)
        row, _ = _ensure_alert(
            db, case=case, source_type="case", source_id=case.id,
            alert_type=LegalAlertType.TERMINAL_MONITORING,
            cycle_key=f"{today.year:04d}-{today.month:02d}", trigger_date=trigger,
            due_date=trigger, responsible_user_id=case.responsible_user_id, today=today,
            allow_new_generation=("case", case.id) in changed_sources,
        )
        generated.append(row)
    return generated


def delivery_stages(alert: LegalCaseAlert, today: date) -> list[str]:
    if alert.status not in ACTIVE_ALERT_STATUSES or today < alert.trigger_date:
        return []
    if alert.alert_type == LegalAlertType.TERMINAL_MONITORING:
        return [f"terminal-{alert.cycle_key}"]
    days_overdue = (today - alert.due_date).days
    if days_overdue < 0: return ["window-entry"]
    if days_overdue == 0: return ["due-date"]
    return [f"overdue-{1 + (days_overdue - 1) // 7}"]


def ensure_due_deliveries(db: Session, alert: LegalCaseAlert, today: date) -> int:
    created = 0
    for stage in delivery_stages(alert, today):
        for channel, initial_status in (
            ("in_app", LegalDeliveryStatus.SENT),
            ("dingtalk", LegalDeliveryStatus.PENDING),
        ):
            existing = db.scalar(select(LegalAlertDelivery).where(
                LegalAlertDelivery.alert_id == alert.id,
                LegalAlertDelivery.channel == channel,
                LegalAlertDelivery.stage_key == stage,
                LegalAlertDelivery.recipient_scope == "legal_group",
            ))
            if existing is None:
                db.add(LegalAlertDelivery(
                    alert_id=alert.id, channel=channel, stage_key=stage,
                    recipient_scope="legal_group", status=initial_status,
                    attempts=1 if channel == "in_app" else 0,
                    first_sent_at=legal_now() if channel == "in_app" else None,
                    last_sent_at=legal_now() if channel == "in_app" else None,
                ))
                created += 1
    db.flush()
    return created


def scan_alerts(db: Session, today: date | None = None) -> AlertScanResult:
    current = today or legal_today()
    cases = db.scalars(
        select(LegalCase).options(
            selectinload(LegalCase.assets),
            selectinload(LegalCase.judgments),
            selectinload(LegalCase.deadlines),
        ).where(
            LegalCase.stage == LegalCaseStage.FORMAL,
            LegalCase.deleted_at.is_(None),
            LegalCase.archived_at.is_(None),
        )
    ).all()
    before_ids = set(db.scalars(select(LegalCaseAlert.id)).all())
    deliveries = 0
    for case in cases:
        alerts = scan_case_alerts(db, case, current)
        for alert in alerts:
            deliveries += ensure_due_deliveries(db, alert, current)
    db.flush()
    after_ids = set(db.scalars(select(LegalCaseAlert.id)).all())
    return AlertScanResult(len(cases), len(after_ids - before_ids), deliveries)


def sync_case_alerts(
    db: Session,
    case: LegalCase,
    today: date | None = None,
) -> list[LegalCaseAlert]:
    db.info.setdefault("legal_alert_case_ids", set()).add(case.id)
    db.flush()
    db.expire(case, ["assets", "judgments", "recoveries", "deadlines"])
    current = today or legal_today()
    alerts = scan_case_alerts(db, case, current)
    for alert in alerts:
        ensure_due_deliveries(db, alert, current)
    return alerts


def complete_source_alerts(db: Session, source_type: str, source_id: int, result: str) -> None:
    rows = db.scalars(select(LegalCaseAlert).where(
        LegalCaseAlert.source_type == source_type,
        LegalCaseAlert.source_id == source_id,
        LegalCaseAlert.status.in_(ACTIVE_ALERT_STATUSES),
    )).all()
    for row in rows:
        row.status = LegalAlertStatus.COMPLETED
        row.result = result
        row.completed_at = legal_now()


def close_source_alerts(db: Session, source_type: str, source_id: int, reason: str) -> None:
    rows = db.scalars(select(LegalCaseAlert).where(
        LegalCaseAlert.source_type == source_type,
        LegalCaseAlert.source_id == source_id,
        LegalCaseAlert.status.in_(ACTIVE_ALERT_STATUSES),
    )).all()
    for row in rows:
        row.status = LegalAlertStatus.CLOSED
        row.result = reason
        row.closed_reason = reason
        row.completed_at = legal_now()


def dispatch_pending_deliveries(
    db: Session,
    client: DingTalkClient | None = None,
    now: datetime | None = None,
    delivery_ids: list[int] | None = None,
) -> int:
    current = now or legal_now()
    sender = client or DingTalkClient()
    ready_conditions = [
        LegalAlertDelivery.status == LegalDeliveryStatus.PENDING,
        (LegalAlertDelivery.status == LegalDeliveryStatus.FAILED)
        & (LegalAlertDelivery.next_retry_at.is_not(None))
        & (LegalAlertDelivery.next_retry_at <= current),
        (LegalAlertDelivery.status == LegalDeliveryStatus.PROCESSING)
        & (LegalAlertDelivery.claim_expires_at.is_not(None))
        & (LegalAlertDelivery.claim_expires_at <= current),
    ]
    if getattr(sender, "configured", True):
        ready_conditions.append(
            LegalAlertDelivery.status == LegalDeliveryStatus.CHANNEL_UNCONFIGURED
        )
    candidate_query = select(LegalAlertDelivery.id).where(
        LegalAlertDelivery.channel == "dingtalk",
        or_(*ready_conditions),
    )
    if delivery_ids is not None:
        candidate_query = candidate_query.where(LegalAlertDelivery.id.in_(delivery_ids))
    candidate_ids = db.scalars(
        candidate_query.order_by(LegalAlertDelivery.id.asc()).limit(100)
    ).all()
    claims: list[tuple[int, str]] = []
    for delivery_id in candidate_ids:
        token = uuid4().hex
        claimed = db.execute(
            update(LegalAlertDelivery)
            .where(
                LegalAlertDelivery.id == delivery_id,
                LegalAlertDelivery.channel == "dingtalk",
                or_(*ready_conditions),
            )
            .values(
                status=LegalDeliveryStatus.PROCESSING,
                claim_token=token,
                claim_expires_at=current + DELIVERY_CLAIM_LEASE,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount == 1:
            claims.append((delivery_id, token))
    db.commit()

    processed = 0
    for delivery_id, token in claims:
        delivery = db.scalar(select(LegalAlertDelivery).where(
            LegalAlertDelivery.id == delivery_id,
            LegalAlertDelivery.status == LegalDeliveryStatus.PROCESSING,
            LegalAlertDelivery.claim_token == token,
        ))
        if delivery is None:
            continue
        alert = db.get(LegalCaseAlert, delivery.alert_id)
        if alert is None or alert.status not in ACTIVE_ALERT_STATUSES:
            delivery.status = LegalDeliveryStatus.CANCELLED
            delivery.response_summary = "预警已关闭，取消投递"
            delivery.claim_token = None
            delivery.claim_expires_at = None
            db.commit()
            continue
        case = db.get(LegalCase, alert.case_id)
        user = db.get(User, alert.responsible_user_id) if alert.responsible_user_id else None
        result = sender.send_alert(alert, case, user)
        delivery.attempts += 1
        delivery.first_sent_at = delivery.first_sent_at or current
        delivery.last_sent_at = current
        delivery.response_summary = result.response_summary[:500]
        delivery.failure_reason = result.failure_reason[:2000]
        if result.success:
            delivery.status = LegalDeliveryStatus.SENT
            delivery.next_retry_at = None
        elif result.status == "channel_unconfigured":
            delivery.status = LegalDeliveryStatus.CHANNEL_UNCONFIGURED
            delivery.next_retry_at = None
        else:
            delivery.status = LegalDeliveryStatus.FAILED
            delivery.next_retry_at = (
                current + RETRY_DELAYS[delivery.attempts - 1]
                if delivery.attempts <= len(RETRY_DELAYS) else None
            )
        delivery.claim_token = None
        delivery.claim_expires_at = None
        db.commit()
        processed += 1
    return processed
