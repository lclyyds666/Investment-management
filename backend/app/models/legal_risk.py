"""投资公司法务风控模块数据模型。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def enum_column(enum_type: type[Enum], *, length: int = 32, **kwargs):
    return mapped_column(
        SAEnum(
            enum_type,
            native_enum=False,
            length=length,
            values_callable=lambda values: [item.value for item in values],
        ),
        **kwargs,
    )


class LegalCaseStage(str, Enum):
    DRAFT = "draft"
    FORMAL = "formal"


class LegalCaseStatus(str, Enum):
    REVIEW_FILING = "review_filing"
    IN_TRIAL = "in_trial"
    JUDGED = "judged"
    ENFORCEMENT = "enforcement"
    TERMINAL = "terminal"
    CLOSED = "closed"


class LegalPartyType(str, Enum):
    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    THIRD_PARTY = "third_party"


class LegalCollaboratorType(str, Enum):
    COLLABORATOR = "collaborator"
    LEGAL_COUNSEL = "legal_counsel"


class LegalJudgmentType(str, Enum):
    FIRST_INSTANCE = "first_instance"
    SECOND_INSTANCE = "second_instance"
    RETRIAL = "retrial"
    MEDIATION = "mediation"
    SETTLEMENT = "settlement"
    EXECUTION = "execution"
    OTHER = "other"


class LegalRecoveryType(str, Enum):
    RECOVERY = "recovery"
    AVOIDED_LOSS = "avoided_loss"


class LegalProgressType(str, Enum):
    PROGRESS = "progress"
    LEGAL_OPINION = "legal_opinion"


class LegalDeadlineType(str, Enum):
    HEARING = "hearing"
    PAYMENT_MATERIAL = "payment_material"
    CUSTOM = "custom"


class LegalAlertType(str, Enum):
    ASSET_EXPIRY = "asset_expiry"
    ENFORCEMENT_APPLICATION = "enforcement_application"
    HEARING = "hearing"
    PAYMENT_MATERIAL = "payment_material"
    CUSTOM = "custom"
    TERMINAL_MONITORING = "terminal_monitoring"


class LegalAlertStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CLOSED = "closed"


class LegalDeliveryStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CHANNEL_UNCONFIGURED = "channel_unconfigured"
    CANCELLED = "cancelled"


class LegalImportStatus(str, Enum):
    PREVIEWED = "previewed"
    IMPORTING = "importing"
    IMPORTED = "imported"
    FAILED = "failed"
    EXPIRED = "expired"


class LegalCase(Base):
    __tablename__ = "legal_case"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stage: Mapped[LegalCaseStage] = enum_column(
        LegalCaseStage, nullable=False, default=LegalCaseStage.DRAFT, index=True
    )
    case_no: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, index=True)
    case_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cause_of_action: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    court: Mapped[str] = mapped_column(String(255), default="", nullable=False, index=True)
    court_case_no: Mapped[str] = mapped_column(String(128), default="", nullable=False, index=True)
    subject_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    status: Mapped[LegalCaseStatus | None] = enum_column(LegalCaseStatus, nullable=True, index=True)
    responsible_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    confidentiality_level: Mapped[str] = mapped_column(String(32), default="internal", nullable=False)
    law_firm: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    attorney_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    case_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    claims: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enforcement_property_status: Mapped[str] = mapped_column(Text, default="", nullable=False)
    terminal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closure_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    archive_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    activated_by: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    parties: Mapped[list["LegalCaseParty"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    collaborators: Mapped[list["LegalCaseCollaborator"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    judgments: Mapped[list["LegalCaseJudgment"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    assets: Mapped[list["LegalCaseAsset"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    recoveries: Mapped[list["LegalCaseRecovery"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    progress_records: Mapped[list["LegalCaseProgress"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    deadlines: Mapped[list["LegalCaseDeadline"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class LegalCaseSequence(Base):
    __tablename__ = "legal_case_sequence"

    year: Mapped[int] = mapped_column(primary_key=True)
    current_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class LegalCaseParty(Base):
    __tablename__ = "legal_case_party"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("legal_case.id", ondelete="CASCADE"), index=True)
    party_type: Mapped[LegalPartyType] = enum_column(LegalPartyType, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    identity_type: Mapped[str] = mapped_column(String(32), default="organization", nullable=False)
    identity_no: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    contact: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    address: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    case: Mapped[LegalCase] = relationship(back_populates="parties")


class LegalCaseCollaborator(Base):
    __tablename__ = "legal_case_collaborator"
    __table_args__ = (
        UniqueConstraint("case_id", "user_id", "collaborator_type", name="uq_legal_case_collaborator"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("legal_case.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), index=True)
    collaborator_type: Mapped[LegalCollaboratorType] = enum_column(LegalCollaboratorType, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), nullable=False)
    case: Mapped[LegalCase] = relationship(back_populates="collaborators")


class LegalCaseJudgment(Base):
    __tablename__ = "legal_case_judgment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("legal_case.id", ondelete="CASCADE"), index=True)
    judgment_type: Mapped[LegalJudgmentType] = enum_column(LegalJudgmentType, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    judgment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    performance_deadline: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    executable_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    is_current_enforcement_basis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    case: Mapped[LegalCase] = relationship(back_populates="judgments")


class LegalCaseAsset(Base):
    __tablename__ = "legal_case_asset"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("legal_case.id", ondelete="CASCADE"), index=True)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(500), nullable=False)
    measure_type: Mapped[str] = mapped_column(String(64), nullable=False)
    priority_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    reminder_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disposal_status: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    case: Mapped[LegalCase] = relationship(back_populates="assets")


class LegalCaseRecovery(Base):
    __tablename__ = "legal_case_recovery"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("legal_case.id", ondelete="CASCADE"), index=True)
    recovery_type: Mapped[LegalRecoveryType] = enum_column(LegalRecoveryType, nullable=False)
    recovery_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    source_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    registered_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    case: Mapped[LegalCase] = relationship(back_populates="recoveries")


class LegalCaseProgress(Base):
    __tablename__ = "legal_case_progress"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("legal_case.id", ondelete="CASCADE"), index=True)
    progress_type: Mapped[LegalProgressType] = enum_column(LegalProgressType, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    risk_points: Mapped[str] = mapped_column(Text, default="", nullable=False)
    next_plan: Mapped[str] = mapped_column(Text, default="", nullable=False)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"), nullable=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    registered_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    case: Mapped[LegalCase] = relationship(back_populates="progress_records")


class LegalCaseDeadline(Base):
    __tablename__ = "legal_case_deadline"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("legal_case.id", ondelete="CASCADE"), index=True)
    deadline_type: Mapped[LegalDeadlineType] = enum_column(LegalDeadlineType, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    reminder_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completion_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    case: Mapped[LegalCase] = relationship(back_populates="deadlines")


class LegalAttachment(Base):
    __tablename__ = "legal_attachment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("legal_case.id", ondelete="CASCADE"), index=True)
    related_type: Mapped[str] = mapped_column(String(32), nullable=False)
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LegalCaseAlert(Base):
    __tablename__ = "legal_case_alert"
    __table_args__ = (
        UniqueConstraint(
            "case_id", "source_type", "source_id", "alert_type", "cycle_key", "generation",
            name="uq_legal_case_alert_cycle",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("legal_case.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_type: Mapped[LegalAlertType] = enum_column(LegalAlertType, nullable=False, index=True)
    cycle_key: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    trigger_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), default="normal", nullable=False, index=True)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"), nullable=True)
    status: Mapped[LegalAlertStatus] = enum_column(
        LegalAlertStatus, nullable=False, default=LegalAlertStatus.PENDING, index=True
    )
    result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)


class LegalAlertDelivery(Base):
    __tablename__ = "legal_alert_delivery"
    __table_args__ = (
        UniqueConstraint(
            "alert_id", "channel", "stage_key", "recipient_scope",
            name="uq_legal_alert_delivery_stage",
        ),
        Index("ix_legal_delivery_claim", "claim_token", "claim_expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("legal_case_alert.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    stage_key: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_scope: Mapped[str] = mapped_column(String(64), default="legal_group", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[LegalDeliveryStatus] = enum_column(
        LegalDeliveryStatus, nullable=False, default=LegalDeliveryStatus.PENDING, index=True
    )
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    response_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    failure_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    first_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class LegalCaseActivity(Base):
    __tablename__ = "legal_case_activity"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("legal_case.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    change_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)


class LegalCaseImportBatch(Base):
    __tablename__ = "legal_case_import_batch"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[LegalImportStatus] = enum_column(
        LegalImportStatus, nullable=False, default=LegalImportStatus.PREVIEWED, index=True
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    importable_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), nullable=False)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LegalCaseImportRow(Base):
    __tablename__ = "legal_case_import_row"
    __table_args__ = (
        UniqueConstraint("batch_id", "sheet_name", "row_number", name="uq_legal_import_row"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("legal_case_import_batch.id", ondelete="CASCADE"), index=True
    )
    sheet_name: Mapped[str] = mapped_column(String(64), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    errors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    imported_case_id: Mapped[int | None] = mapped_column(ForeignKey("legal_case.id"), nullable=True)
