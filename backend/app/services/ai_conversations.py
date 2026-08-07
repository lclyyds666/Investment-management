"""Conversation ownership, persistence helpers, and safe starter prompts."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AsyncIterator
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.enums import CompanyCode, ResourceCode
from app.models.ai_assistant import AiConversation, AiDeletionAudit, AiMessage
from app.schemas.ai_assistant import ScenicNavigationAction
from app.models.user import User
from app.services import ai_runtime
from app.services.ai_orchestrator import (
    AiOrchestrator,
    LOCAL_ENGINE,
    MODEL_ENGINE,
    _UNAVAILABLE,
    is_safe_model_text,
)
from app.services.ai_tools import ToolContext
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
logger = logging.getLogger("app.ai_assistant")
_MAX_UNTRUSTED_OUTPUT_CHARS = 4096
_GENERATION_STOP_WAIT_SECONDS = 0.5
_GENERATION_STOP_POLL_SECONDS = 0.05
_RETENTION_BATCH_SIZE = 500
_RETENTION_SCAN_CHUNK_SIZE = 500


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


def list_admin_conversations(
    db: Session,
    *,
    user_id: int | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    conversation_status: str | None = None,
    keyword: str | None = None,
    page: int,
    size: int,
) -> tuple[list[AiConversation], int]:
    conditions = []
    if user_id is not None:
        conditions.append(AiConversation.owner_id == user_id)
    if started_at is not None:
        conditions.append(AiConversation.created_at >= started_at)
    if ended_at is not None:
        conditions.append(AiConversation.created_at <= ended_at)
    if conversation_status:
        conditions.append(AiConversation.status == conversation_status)
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        message_match = select(AiMessage.id).where(
            AiMessage.conversation_id == AiConversation.id,
            AiMessage.content.ilike(pattern),
        ).exists()
        conditions.append(or_(AiConversation.title.ilike(pattern), message_match))

    statement = (
        select(AiConversation)
        .where(*conditions)
        .order_by(AiConversation.last_active_at.desc(), AiConversation.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = db.scalars(statement).all()
    total = db.scalar(
        select(func.count()).select_from(AiConversation).where(*conditions)
    ) or 0
    return rows, total


def get_admin_conversation(db: Session, conversation_id: int) -> AiConversation:
    conversation = db.scalar(
        select(AiConversation)
        .options(
            selectinload(AiConversation.messages).selectinload(AiMessage.tool_calls)
        )
        .where(AiConversation.id == conversation_id)
    )
    if conversation is None:
        raise _not_found()
    return conversation


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


def _request_stop_for_generating_messages(conversation: AiConversation) -> None:
    for message in conversation.messages:
        if message.role != "assistant" or message.status != "generating":
            continue
        ai_runtime.request_stop(message.id)


def _conversation_busy() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "conversation_busy", "message": "该会话正在生成回复"},
    )


def _reserve_conversation_for_deletion(
    conversation: AiConversation,
) -> ai_runtime.DeletionReservation:
    _request_stop_for_generating_messages(conversation)
    deadline = time.monotonic() + _GENERATION_STOP_WAIT_SECONDS
    while True:
        reservation = ai_runtime.try_acquire_deletion_reservation(conversation.id)
        if reservation is not None:
            return reservation
        if time.monotonic() >= deadline:
            raise _conversation_busy()
        time.sleep(_GENERATION_STOP_POLL_SECONDS)


def _reload_messages_under_reservation(
    db: Session, conversation: AiConversation
) -> list[AiMessage]:
    db.expire(conversation, ["messages"])
    return list(conversation.messages)


def delete_owned_conversation(
    db: Session, conversation_id: int, user_id: int
) -> AiDeletionAudit:
    conversation = get_owned_conversation(db, conversation_id, user_id, with_messages=True)
    reservation = _reserve_conversation_for_deletion(conversation)
    heartbeat = ai_runtime.DeletionReservationHeartbeat([reservation])
    try:
        heartbeat.start()
        messages = _reload_messages_under_reservation(db, conversation)
        receipt = AiDeletionAudit(
            conversation_id=conversation.id,
            owner_id=conversation.owner_id,
            actor_id=user_id,
            mode="owner",
            reason="用户主动删除",
            deleted_message_count=len(messages),
            deleted_at=datetime.now(),
        )
        db.add(receipt)
        db.delete(conversation)
        heartbeat.assert_owned()
        db.commit()
    except ai_runtime.LeaseOwnershipLost as exc:
        db.rollback()
        raise _conversation_busy() from exc
    except Exception:
        db.rollback()
        raise
    finally:
        heartbeat.stop()
        ai_runtime.release_deletion_reservation(reservation)
    return receipt


def delete_admin_conversation(
    db: Session,
    conversation_id: int,
    actor_id: int,
    reason: str,
) -> AiDeletionAudit:
    conversation = get_admin_conversation(db, conversation_id)
    reservation = _reserve_conversation_for_deletion(conversation)
    heartbeat = ai_runtime.DeletionReservationHeartbeat([reservation])
    try:
        heartbeat.start()
        messages = _reload_messages_under_reservation(db, conversation)
        receipt = AiDeletionAudit(
            conversation_id=conversation.id,
            owner_id=conversation.owner_id,
            actor_id=actor_id,
            mode="admin",
            reason=reason,
            deleted_message_count=len(messages),
            deleted_at=datetime.now(),
        )
        db.add(receipt)
        db.delete(conversation)
        heartbeat.assert_owned()
        db.commit()
    except ai_runtime.LeaseOwnershipLost as exc:
        db.rollback()
        raise _conversation_busy() from exc
    except Exception:
        db.rollback()
        raise
    finally:
        heartbeat.stop()
        ai_runtime.release_deletion_reservation(reservation)
    db.refresh(receipt)
    return receipt


def list_deletion_audits(
    db: Session,
    *,
    user_id: int | None = None,
    mode: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    page: int,
    size: int,
) -> tuple[list[AiDeletionAudit], int]:
    conditions = []
    if user_id is not None:
        conditions.append(AiDeletionAudit.owner_id == user_id)
    if mode:
        conditions.append(AiDeletionAudit.mode == mode)
    if started_at is not None:
        conditions.append(AiDeletionAudit.deleted_at >= started_at)
    if ended_at is not None:
        conditions.append(AiDeletionAudit.deleted_at <= ended_at)
    rows = db.scalars(
        select(AiDeletionAudit)
        .where(*conditions)
        .order_by(AiDeletionAudit.deleted_at.desc(), AiDeletionAudit.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    total = db.scalar(
        select(func.count()).select_from(AiDeletionAudit).where(*conditions)
    ) or 0
    return rows, total


@dataclass(frozen=True)
class CleanupResult:
    deleted_conversations: int
    deleted_messages: int


def _expired_conversation_page(
    db: Session,
    *,
    now: datetime,
    cursor: tuple[datetime, int] | None,
) -> list[AiConversation]:
    cutoff = now - timedelta(days=settings.AI_CONVERSATION_RETENTION_DAYS)
    conditions = [AiConversation.last_active_at < cutoff]
    if cursor is not None:
        last_active_at, conversation_id = cursor
        conditions.append(or_(
            AiConversation.last_active_at > last_active_at,
            and_(
                AiConversation.last_active_at == last_active_at,
                AiConversation.id > conversation_id,
            ),
        ))
    return db.scalars(
        select(AiConversation)
        .options(selectinload(AiConversation.messages))
        .where(*conditions)
        .order_by(AiConversation.last_active_at, AiConversation.id)
        .limit(_RETENTION_SCAN_CHUNK_SIZE)
    ).all()


def _scan_expired_conversations(
    db: Session,
    *,
    now: datetime,
    reserve_for_deletion: bool,
    reservations: list[ai_runtime.DeletionReservation] | None = None,
    heartbeat: ai_runtime.DeletionReservationHeartbeat | None = None,
) -> list[AiConversation]:
    selected: list[AiConversation] = []
    cursor: tuple[datetime, int] | None = None
    while len(selected) < _RETENTION_BATCH_SIZE:
        page = _expired_conversation_page(db, now=now, cursor=cursor)
        if not page:
            break

        for conversation in page:
            if reserve_for_deletion:
                if reservations is None or heartbeat is None:
                    raise RuntimeError("retention deletion requires a reservation heartbeat")
                reservation = ai_runtime.try_acquire_deletion_reservation(
                    conversation.id
                )
                if reservation is None:
                    continue
                reservations.append(reservation)
                heartbeat.add(reservation)
                _reload_messages_under_reservation(db, conversation)
            elif ai_runtime.is_conversation_occupied(conversation.id):
                continue

            selected.append(conversation)
            if len(selected) == _RETENTION_BATCH_SIZE:
                break

        if len(page) < _RETENTION_SCAN_CHUNK_SIZE:
            break
        last = page[-1]
        cursor = (last.last_active_at, last.id)
    return selected


def preview_expired_conversations(
    db: Session, *, now: datetime
) -> CleanupResult:
    rows = _scan_expired_conversations(
        db, now=now, reserve_for_deletion=False
    )
    return CleanupResult(
        deleted_conversations=len(rows),
        deleted_messages=sum(len(row.messages) for row in rows),
    )


def cleanup_expired_conversations(
    db: Session, *, now: datetime
) -> CleanupResult:
    rows: list[AiConversation] = []
    reservations: list[ai_runtime.DeletionReservation] = []
    heartbeat = ai_runtime.DeletionReservationHeartbeat()
    try:
        heartbeat.start()
        rows = _scan_expired_conversations(
            db,
            now=now,
            reserve_for_deletion=True,
            reservations=reservations,
            heartbeat=heartbeat,
        )
        deleted_messages = sum(len(row.messages) for row in rows)
        for conversation in rows:
            db.add(AiDeletionAudit(
                conversation_id=conversation.id,
                owner_id=conversation.owner_id,
                actor_id=None,
                mode="retention",
                reason="超过当前会话保留期",
                deleted_message_count=len(conversation.messages),
                deleted_at=now,
            ))
            db.delete(conversation)
        if rows:
            heartbeat.assert_owned()
            db.commit()
    except ai_runtime.LeaseOwnershipLost:
        db.rollback()
        return CleanupResult(deleted_conversations=0, deleted_messages=0)
    except Exception:
        db.rollback()
        raise
    finally:
        heartbeat.stop()
        for reservation in reservations:
            ai_runtime.release_deletion_reservation(reservation)
    return CleanupResult(
        deleted_conversations=len(rows),
        deleted_messages=deleted_messages,
    )


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


def encode_sse(event: str, payload: dict) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n"


def _duplicate_submission(
    db: Session, conversation_id: int, client_message_id: UUID
) -> bool:
    return db.scalar(
        select(AiMessage.id).where(
            AiMessage.conversation_id == conversation_id,
            AiMessage.client_message_id == str(client_message_id),
        )
    ) is not None


def begin_generation(
    db: Session,
    conversation: AiConversation,
    user_id: int,
    content: str,
    client_message_id: UUID,
) -> tuple[AiMessage, AiMessage, ai_runtime.GenerationLease, str]:
    if _duplicate_submission(db, conversation.id, client_message_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "duplicate_submission", "message": "消息已提交"},
        )

    ai_runtime.check_submission_rate(user_id)
    request_id = str(uuid4())
    lease = ai_runtime.acquire_generation(user_id, conversation.id, request_id)
    user_message = AiMessage(
        conversation_id=conversation.id,
        role="user",
        content=content,
        status="completed",
        client_message_id=str(client_message_id),
        request_id=request_id,
        actions_json=[],
    )
    assistant_message = AiMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="",
        status="generating",
        request_id=request_id,
        actions_json=[],
    )
    try:
        db.add_all([user_message, assistant_message])
        db.commit()
        db.refresh(user_message)
        db.refresh(assistant_message)
    except IntegrityError as exc:
        db.rollback()
        ai_runtime.release_generation(lease)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "duplicate_submission", "message": "消息已提交"},
        ) from exc
    except Exception:
        db.rollback()
        ai_runtime.release_generation(lease)
        raise
    return user_message, assistant_message, lease, request_id


def _iso_date(value):
    if value is None or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _iso_datetime(value):
    if value is None or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _apply_metadata(message: AiMessage, metadata: dict) -> None:
    message.data_start_date = _iso_date(metadata.get("data_start_date"))
    message.data_end_date = _iso_date(metadata.get("data_end_date"))
    message.data_covered_start = _iso_date(metadata.get("data_covered_start"))
    message.data_covered_end = _iso_date(metadata.get("data_covered_end"))
    message.data_updated_at = _iso_datetime(metadata.get("data_updated_at"))


def _event_payload(request_id: str, message_id: int, payload: dict | None = None) -> dict:
    return {"request_id": request_id, "message_id": message_id, **(payload or {})}


async def stream_generation(
    *,
    db: Session,
    conversation: AiConversation,
    user_message: AiMessage,
    assistant_message: AiMessage,
    lease: ai_runtime.GenerationLease,
    request_id: str,
    request,
    user: User,
) -> AsyncIterator[str]:
    started = time.perf_counter()
    content_parts: list[str] = []
    actions: list[dict] = []
    engine: str | None = None
    first_token_ms: int | None = None
    metadata: dict = {}
    terminal_status = "completed"
    error_code: str | None = None
    terminal_payload: dict = {}
    cancelled = False
    task_cancelled = False
    untrusted_parts: list[str] = []
    heartbeat = ai_runtime.generation_heartbeat(lease)

    try:
        heartbeat.start()
        try:
            yield encode_sse("message.created", _event_payload(request_id, assistant_message.id, {
                "conversation_id": conversation.id,
                "user_message_id": user_message.id,
                "status": "generating",
            }))

            context = ToolContext(
                db=db,
                user=user,
                request_id=request_id,
                message_id=assistant_message.id,
            )
            async for event in AiOrchestrator().stream(user_message.content, context):
                if heartbeat.ownership_lost:
                    raise ai_runtime.LeaseOwnershipLost(
                        "generation lease ownership was lost"
                    )
                if await request.is_disconnected() or ai_runtime.is_stop_requested(assistant_message.id):
                    terminal_status = "stopped"
                    break

                if event.kind == "text.delta":
                    text = str(event.payload.get("text", ""))
                    event_engine = event.payload.get("engine")
                    if event_engine != LOCAL_ENGINE and not (
                        event_engine == MODEL_ENGINE
                        and event.payload.get("validated") is True
                        and is_safe_model_text(text)
                    ):
                        if text:
                            untrusted_parts.append(text)
                            combined = "".join(untrusted_parts)
                            if (
                                len(combined) > _MAX_UNTRUSTED_OUTPUT_CHARS
                                or not is_safe_model_text(combined)
                            ):
                                break
                        continue
                    if text:
                        if first_token_ms is None:
                            first_token_ms = max(0, round((time.perf_counter() - started) * 1000))
                        content_parts.append(text)
                    engine = event_engine if event_engine == MODEL_ENGINE else LOCAL_ENGINE
                    yield encode_sse("text.delta", _event_payload(
                        request_id, assistant_message.id, {"text": text}
                    ))
                    continue

                if event.kind == "action":
                    action = ScenicNavigationAction.model_validate(event.payload).model_dump(mode="json")
                    actions.append(action)
                    yield encode_sse("action", _event_payload(
                        request_id, assistant_message.id, {"action": action}
                    ))
                    continue

                if event.kind == "tool.status":
                    if isinstance(event.payload.get("metadata"), dict):
                        metadata.update(event.payload["metadata"])
                    yield encode_sse("tool.status", _event_payload(
                        request_id, assistant_message.id, event.payload
                    ))
                    continue

                if event.kind == "error":
                    terminal_status = "failed"
                    error_code = str(event.payload.get("code") or "generation_failed")[:64]
                    terminal_payload = {
                        "code": error_code,
                        "message": str(event.payload.get("message") or "AI 服务暂时不可用，请稍后重试。"),
                    }
                    break
            if terminal_status == "completed" and (
                await request.is_disconnected()
                or ai_runtime.is_stop_requested(assistant_message.id)
            ):
                terminal_status = "stopped"
            if terminal_status == "completed" and untrusted_parts:
                if first_token_ms is None:
                    first_token_ms = max(0, round((time.perf_counter() - started) * 1000))
                content_parts.append(_UNAVAILABLE)
                engine = LOCAL_ENGINE
                yield encode_sse("text.delta", _event_payload(
                    request_id, assistant_message.id, {"text": _UNAVAILABLE}
                ))
        except asyncio.CancelledError:
            terminal_status = "stopped"
            cancelled = True
            task_cancelled = True
        except GeneratorExit:
            terminal_status = "stopped"
            cancelled = True
        except ai_runtime.LeaseOwnershipLost:
            raise
        except Exception:
            logger.exception("ai_generation_failed", extra={
                "request_id": request_id,
                "message_id": assistant_message.id,
            })
            terminal_status = "failed"
            error_code = "generation_failed"
            terminal_payload = {
                "code": error_code,
                "message": "AI 服务暂时不可用，请稍后重试。",
            }

        assistant_message.content = "".join(content_parts)
        assistant_message.actions_json = actions
        assistant_message.status = terminal_status
        assistant_message.engine = engine
        assistant_message.first_token_ms = first_token_ms
        assistant_message.duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        assistant_message.error_code = error_code
        _apply_metadata(assistant_message, metadata)

        now = datetime.now()
        conversation.last_active_at = now
        conversation.expires_at = now + timedelta(days=settings.AI_CONVERSATION_RETENTION_DAYS)
        if terminal_status == "completed":
            set_generated_title(conversation, user_message.content)
        heartbeat.assert_owned()
        db.commit()

        logger.info("ai_generation_completed", extra={
            "request_id": request_id,
            "message_id": assistant_message.id,
            "conversation_id": conversation.id,
            "status": terminal_status,
            "engine": engine,
            "duration_ms": assistant_message.duration_ms,
            "error_code": error_code,
        })

        if not cancelled:
            terminal_event = {
                "completed": "message.completed",
                "stopped": "message.stopped",
                "failed": "error",
            }[terminal_status]
            yield encode_sse(terminal_event, _event_payload(
                request_id,
                assistant_message.id,
                {"status": terminal_status, **terminal_payload},
            ))
    except Exception:
        db.rollback()
        logger.exception("ai_generation_settlement_failed", extra={
            "request_id": request_id,
            "message_id": assistant_message.id,
        })
        if not cancelled:
            yield encode_sse("error", _event_payload(request_id, assistant_message.id, {
                "status": "failed",
                "code": "persistence_failed",
                "message": "AI 服务暂时不可用，请稍后重试。",
            }))
    finally:
        heartbeat.stop()
        ai_runtime.clear_stop_request(assistant_message.id)
        ai_runtime.release_generation(lease)

    if task_cancelled:
        raise asyncio.CancelledError()
    if cancelled:
        return
