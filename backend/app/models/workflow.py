from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    WorkflowAction,
    WorkflowAssigneeMode,
    WorkflowInstanceStatus,
    WorkflowTargetType,
    WorkflowTaskStatus,
    WorkflowVersionStatus,
)
from app.db.base import Base


SignatureText = Text().with_variant(MEDIUMTEXT, "mysql")


def enum_column(enum_type, length: int):
    return SAEnum(
        enum_type,
        native_enum=False,
        length=length,
        values_callable=lambda enum: [item.value for item in enum],
    )


class WorkflowDefinition(Base):
    __tablename__ = "wf_definition"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[WorkflowTargetType] = mapped_column(
        enum_column(WorkflowTargetType, 24), nullable=False, index=True
    )
    active_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("wf_version.id", ondelete="SET NULL", use_alter=True), nullable=True
    )

    versions = relationship(
        "WorkflowVersion",
        back_populates="definition",
        foreign_keys="WorkflowVersion.definition_id",
    )
    active_version = relationship(
        "WorkflowVersion",
        foreign_keys=[active_version_id],
        post_update=True,
    )


class WorkflowVersion(Base):
    __tablename__ = "wf_version"
    __table_args__ = (
        UniqueConstraint(
            "definition_id",
            "version",
            name="uq_workflow_version_definition_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("wf_definition.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[WorkflowVersionStatus] = mapped_column(
        enum_column(WorkflowVersionStatus, 16),
        default=WorkflowVersionStatus.DRAFT,
        nullable=False,
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True
    )

    definition = relationship(
        "WorkflowDefinition",
        back_populates="versions",
        foreign_keys=[definition_id],
    )
    nodes = relationship(
        "WorkflowNode",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="WorkflowNode.sequence",
    )
    publisher = relationship("User", foreign_keys=[published_by])


class WorkflowNode(Base):
    __tablename__ = "wf_node"
    __table_args__ = (
        UniqueConstraint("version_id", "sequence", name="uq_workflow_node_version_sequence"),
        UniqueConstraint("version_id", "code", name="uq_workflow_node_version_code"),
        Index("idx_workflow_node_position", "position_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("wf_version.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(96), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    position_code: Mapped[str] = mapped_column(String(96), nullable=False)
    assignee_mode: Mapped[WorkflowAssigneeMode] = mapped_column(
        enum_column(WorkflowAssigneeMode, 24), nullable=False
    )
    candidate_rule: Mapped[str] = mapped_column(
        String(32), default="position", nullable=False
    )
    candidate_position_codes: Mapped[list[str] | None] = mapped_column(
        JSON, default=list, nullable=True
    )
    auto_complete_on_submit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_reject: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    version = relationship("WorkflowVersion", back_populates="nodes")


class WorkflowInstance(Base):
    __tablename__ = "wf_instance"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uq_workflow_instance_target"),
        Index("idx_workflow_instance_status_sequence", "status", "current_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("wf_definition.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version_id: Mapped[int] = mapped_column(
        ForeignKey("wf_version.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_type: Mapped[WorkflowTargetType] = mapped_column(
        enum_column(WorkflowTargetType, 24), nullable=False
    )
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[WorkflowInstanceStatus] = mapped_column(
        enum_column(WorkflowInstanceStatus, 16),
        default=WorkflowInstanceStatus.ACTIVE,
        nullable=False,
    )
    current_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submitted_by: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    definition = relationship("WorkflowDefinition", foreign_keys=[definition_id])
    workflow_version = relationship("WorkflowVersion", foreign_keys=[version_id])
    submitter = relationship("User", foreign_keys=[submitted_by])
    tasks = relationship("WorkflowTask", back_populates="instance", cascade="all, delete-orphan")


class WorkflowTask(Base):
    __tablename__ = "wf_task"
    __table_args__ = (
        UniqueConstraint("instance_id", "node_id", name="uq_workflow_task_instance_node"),
        Index("idx_workflow_task_status_position", "status", "required_position_code"),
        Index("idx_workflow_task_designated_user_status", "designated_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("wf_instance.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[int] = mapped_column(
        ForeignKey("wf_node.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[WorkflowTaskStatus] = mapped_column(
        enum_column(WorkflowTaskStatus, 24),
        default=WorkflowTaskStatus.PENDING,
        nullable=False,
    )
    required_position_code: Mapped[str] = mapped_column(String(96), nullable=False)
    required_position_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    assignee_mode: Mapped[WorkflowAssigneeMode] = mapped_column(
        enum_column(WorkflowAssigneeMode, 24), nullable=False
    )
    designated_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True
    )
    designated_assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user_assignment.id", ondelete="SET NULL"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    instance = relationship("WorkflowInstance", back_populates="tasks")
    node = relationship("WorkflowNode")
    designated_user = relationship("User", foreign_keys=[designated_user_id])
    designated_assignment = relationship("UserAssignment", foreign_keys=[designated_assignment_id])
    actions = relationship("WorkflowTaskAction", back_populates="task", cascade="all, delete-orphan")


class WorkflowTaskAction(Base):
    __tablename__ = "wf_task_action"
    __table_args__ = (Index("idx_workflow_task_action_task_created", "task_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("wf_task.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[WorkflowAction] = mapped_column(enum_column(WorkflowAction, 16), nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(128), nullable=False)
    organization_code: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    organization_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    position_code: Mapped[str] = mapped_column(String(96), default="", nullable=False)
    position_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    signature_snapshot: Mapped[str | None] = mapped_column(SignatureText, nullable=True)
    previous_assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True
    )
    previous_assignee_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    new_assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True
    )
    new_assignee_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    returned_to_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    task = relationship("WorkflowTask", back_populates="actions")
    actor = relationship("User", foreign_keys=[actor_id])
    previous_assignee = relationship("User", foreign_keys=[previous_assignee_id])
    new_assignee = relationship("User", foreign_keys=[new_assignee_id])
