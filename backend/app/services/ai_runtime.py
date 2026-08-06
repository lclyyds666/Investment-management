"""Shared coordination state for AI generation requests."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.store import store as runtime_store


@dataclass(frozen=True)
class GenerationLease:
    user_id: int
    conversation_id: int
    request_id: str


def _conversation_key(conversation_id: int) -> str:
    return f"ai:conversation:{conversation_id}:lease"


def _active_key(user_id: int) -> str:
    return f"ai:user:{user_id}:active"


def acquire_generation(user_id: int, conversation_id: int, request_id: str) -> GenerationLease:
    ttl = settings.AI_GENERATION_LEASE_SECONDS
    conversation_key = _conversation_key(conversation_id)
    if not runtime_store.set_if_absent(conversation_key, request_id, ttl):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该会话正在生成回复")

    if not runtime_store.set_members(
        _active_key(user_id), request_id, settings.AI_MAX_CONCURRENT_PER_USER, ttl
    ):
        runtime_store.compare_delete(conversation_key, request_id)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="同时生成的会话过多")

    return GenerationLease(user_id=user_id, conversation_id=conversation_id, request_id=request_id)


def release_generation(lease: GenerationLease) -> None:
    runtime_store.compare_delete(_conversation_key(lease.conversation_id), lease.request_id)
    runtime_store.remove_member(_active_key(lease.user_id), lease.request_id)


def check_submission_rate(user_id: int) -> None:
    count = runtime_store.incr(f"ai:user:{user_id}:rate", ttl=60)
    if count > settings.AI_REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="消息发送过于频繁")


def request_stop(message_id: int) -> None:
    runtime_store.set(
        f"ai:message:{message_id}:stop",
        "1",
        ttl=settings.AI_GENERATION_LEASE_SECONDS,
    )


def is_stop_requested(message_id: int) -> bool:
    return runtime_store.get(f"ai:message:{message_id}:stop") == "1"


def reset_for_tests() -> None:
    runtime_store.clear_prefix("ai:")
