"""Persistence models for AI conversations and content-free deletion receipts."""
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AiConversation(Base):
    __tablename__ = "ai_conversation"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(120), default="新会话", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    messages: Mapped[list["AiMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AiMessage.id",
    )


class AiMessage(Base):
    __tablename__ = "ai_message"
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_message_id", name="uq_ai_message_client"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    data_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_covered_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_covered_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    engine: Mapped[str | None] = mapped_column(String(24), nullable=True)
    first_token_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    conversation: Mapped[AiConversation] = relationship(back_populates="messages")
    tool_calls: Mapped[list["AiToolCall"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AiToolCall.id",
    )


class AiToolCall(Base):
    __tablename__ = "ai_tool_call"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("ai_message.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    permission_decision: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    message: Mapped[AiMessage] = relationship(back_populates="tool_calls")


class AiDeletionAudit(Base):
    __tablename__ = "ai_deletion_audit"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    deleted_message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
