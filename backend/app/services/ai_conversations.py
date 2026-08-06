"""Conversation ownership, persistence helpers, and safe starter prompts."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.enums import CompanyCode, ResourceCode
from app.models.ai_assistant import AiConversation, AiDeletionAudit
from app.models.user import User
from app.services.permissions import has_resource

_DEFAULT_TITLE = "新会话"
_PLATFORM_SUGGESTIONS = [
    "这个平台是干什么的？",
    "介绍一下三个业务系统的建设情况。",
]
_SCENIC_SUGGESTIONS = [
    "遵义动物园上个月经营数据。",
    "对比遵义动物园和南阳森林野生动物世界今年经营数据。",
]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")


def get_owned_conversation(
    db: Session,
    conversation_id: int,
    user_id: int,
    *,
    with_messages: bool = False,
    is_information_maintainer: bool = False,
) -> AiConversation:
    """Return an owned conversation, or a maintainer-visible one, without ID enumeration."""
    if with_messages:
        statement = select(AiConversation).options(selectinload(AiConversation.messages)).where(
            AiConversation.id == conversation_id
        )
        if not is_information_maintainer:
            statement = statement.where(AiConversation.owner_id == user_id)
        conversation = db.scalar(statement)
    else:
        conversation = db.get(AiConversation, conversation_id)
        if (
            conversation is not None
            and conversation.owner_id != user_id
            and not is_information_maintainer
        ):
            conversation = None
    if conversation is None:
        raise _not_found()
    return conversation


def list_owned_conversations(
    db: Session, user_id: int, *, page: int, size: int
) -> tuple[list[AiConversation], int]:
    statement = (
        select(AiConversation)
        .where(AiConversation.owner_id == user_id)
        .order_by(AiConversation.last_active_at.desc(), AiConversation.id.desc())
    )
    rows = db.scalars(statement.offset((page - 1) * size).limit(size)).all()
    total = db.scalar(
        select(func.count()).select_from(AiConversation).where(AiConversation.owner_id == user_id)
    ) or 0
    return rows, total


def create_conversation(db: Session, user_id: int, title: str = _DEFAULT_TITLE) -> AiConversation:
    now = datetime.now()
    conversation = AiConversation(
        owner_id=user_id,
        title=title,
        status="active",
        last_active_at=now,
        expires_at=now + timedelta(days=settings.AI_CONVERSATION_RETENTION_DAYS),
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def rename_owned_conversation(
    db: Session, conversation_id: int, user_id: int, title: str
) -> AiConversation:
    conversation = get_owned_conversation(db, conversation_id, user_id)
    conversation.title = title
    db.commit()
    db.refresh(conversation)
    return conversation


def delete_owned_conversation(
    db: Session, conversation_id: int, user_id: int
) -> AiDeletionAudit:
    conversation = get_owned_conversation(db, conversation_id, user_id, with_messages=True)
    receipt = AiDeletionAudit(
        conversation_id=conversation.id,
        owner_id=conversation.owner_id,
        actor_id=user_id,
        mode="owner",
        reason="用户主动删除",
        deleted_message_count=len(conversation.messages),
        deleted_at=datetime.now(),
    )
    try:
        db.add(receipt)
        db.delete(conversation)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return receipt


def suggestions_for_user(db: Session, user: User) -> list[str]:
    questions = list(_PLATFORM_SUGGESTIONS)
    if has_resource(
        db, user, CompanyCode.SUPPLY_MANAGEMENT, ResourceCode.SCENIC_ANALYTICS
    ):
        questions.extend(_SCENIC_SUGGESTIONS)
    return questions


def title_from_question(question: str) -> str:
    """Make the first visible question text a concise, markup-free conversation title."""
    text = re.sub(r"!?(?:\[([^\]]*)\]\([^)]*\))", r"\1", question or "")
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"[`*_~>#]", "", text)
    text = " ".join(text.split())
    return text[:24] or _DEFAULT_TITLE


def set_generated_title(conversation: AiConversation, question: str) -> None:
    """Set the automatic title once, after the first completed question/answer pair."""
    if conversation.title == _DEFAULT_TITLE:
        conversation.title = title_from_question(question)
