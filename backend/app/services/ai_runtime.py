"""Shared coordination state for AI generation requests."""
from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.store import store as runtime_store


@dataclass(frozen=True)
class GenerationLease:
    user_id: int
    conversation_id: int
    request_id: str


@dataclass(frozen=True)
class DeletionReservation:
    conversation_id: int
    token: str


_DELETION_RESERVATION_PREFIX = "deletion:"


class LeaseOwnershipLost(RuntimeError):
    """Raised when a heartbeat can no longer prove token ownership."""


class LeaseHeartbeat:
    """Renew an owned coordination token and remember any ownership loss."""

    def __init__(
        self,
        renew_owned: Callable[[], bool],
        *,
        interval_seconds: float | None = None,
    ) -> None:
        ttl = settings.AI_GENERATION_LEASE_SECONDS
        self._renew_owned = renew_owned
        self._interval_seconds = interval_seconds or max(0.05, ttl / 3)
        self._stop_event = threading.Event()
        self._lost_event = threading.Event()
        self._renew_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def ownership_lost(self) -> bool:
        return self._lost_event.is_set()

    def renew_now(self) -> bool:
        with self._renew_lock:
            if self.ownership_lost:
                return False
            try:
                owned = self._renew_owned()
            except Exception:
                owned = False
            if not owned:
                self._lost_event.set()
            return owned

    def assert_owned(self) -> None:
        if not self.renew_now():
            raise LeaseOwnershipLost("conversation coordination ownership was lost")

    def start(self) -> None:
        self.assert_owned()
        self._thread = threading.Thread(
            target=self._run,
            name="ai-lease-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            if not self.renew_now():
                return

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()


class DeletionReservationHeartbeat:
    """Use one heartbeat thread for a changing batch of deletion reservations."""

    def __init__(
        self,
        reservations: Iterable[DeletionReservation] = (),
        *,
        interval_seconds: float | None = None,
    ) -> None:
        self._reservations = list(reservations)
        self._reservations_lock = threading.Lock()
        self._heartbeat = LeaseHeartbeat(
            self._renew_all,
            interval_seconds=interval_seconds,
        )

    @property
    def ownership_lost(self) -> bool:
        return self._heartbeat.ownership_lost

    def add(self, reservation: DeletionReservation) -> None:
        if self.ownership_lost:
            raise LeaseOwnershipLost("deletion reservation ownership was lost")
        with self._reservations_lock:
            self._reservations.append(reservation)

    def _renew_all(self) -> bool:
        with self._reservations_lock:
            reservations = list(self._reservations)
        owned = True
        for reservation in reservations:
            if not renew_deletion_reservation(reservation):
                owned = False
        return owned

    def start(self) -> None:
        self._heartbeat.start()

    def assert_owned(self) -> None:
        self._heartbeat.assert_owned()

    def stop(self) -> None:
        self._heartbeat.stop()


def _conversation_key(conversation_id: int) -> str:
    return f"ai:conversation:{conversation_id}:lease"


def _active_key(user_id: int) -> str:
    return f"ai:user:{user_id}:active"


def acquire_generation(user_id: int, conversation_id: int, request_id: str) -> GenerationLease:
    ttl = settings.AI_GENERATION_LEASE_SECONDS
    conversation_key = _conversation_key(conversation_id)
    if not runtime_store.set_if_absent(conversation_key, request_id, ttl):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "conversation_busy", "message": "该会话正在生成回复"},
        )

    try:
        admitted = runtime_store.set_members(
            _active_key(user_id),
            request_id,
            settings.AI_MAX_CONCURRENT_PER_USER,
            ttl,
        )
    except Exception:
        runtime_store.compare_delete(conversation_key, request_id)
        raise

    if not admitted:
        runtime_store.compare_delete(conversation_key, request_id)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="同时生成的会话过多")

    return GenerationLease(user_id=user_id, conversation_id=conversation_id, request_id=request_id)


def release_generation(lease: GenerationLease) -> None:
    runtime_store.compare_delete(_conversation_key(lease.conversation_id), lease.request_id)
    runtime_store.remove_member(_active_key(lease.user_id), lease.request_id)


def renew_generation(lease: GenerationLease) -> bool:
    ttl = settings.AI_GENERATION_LEASE_SECONDS
    if not runtime_store.compare_expire(
        _conversation_key(lease.conversation_id), lease.request_id, ttl
    ):
        return False
    return runtime_store.renew_member(
        _active_key(lease.user_id),
        lease.request_id,
        ttl,
    )


def generation_heartbeat(lease: GenerationLease) -> LeaseHeartbeat:
    return LeaseHeartbeat(lambda: renew_generation(lease))


def is_generation_active(conversation_id: int) -> bool:
    """Return whether a conversation currently holds a generation lease."""
    value = runtime_store.get(_conversation_key(conversation_id))
    return value is not None and not value.startswith(_DELETION_RESERVATION_PREFIX)


def is_conversation_occupied(conversation_id: int) -> bool:
    """Return whether generation or deletion currently owns the coordination key."""
    return runtime_store.get(_conversation_key(conversation_id)) is not None


def try_acquire_deletion_reservation(
    conversation_id: int,
) -> DeletionReservation | None:
    token = f"{_DELETION_RESERVATION_PREFIX}{uuid4()}"
    if not runtime_store.set_if_absent(
        _conversation_key(conversation_id),
        token,
        settings.AI_GENERATION_LEASE_SECONDS,
    ):
        return None
    return DeletionReservation(conversation_id=conversation_id, token=token)


def release_deletion_reservation(reservation: DeletionReservation) -> None:
    runtime_store.compare_delete(
        _conversation_key(reservation.conversation_id), reservation.token
    )


def renew_deletion_reservation(reservation: DeletionReservation) -> bool:
    return runtime_store.compare_expire(
        _conversation_key(reservation.conversation_id),
        reservation.token,
        settings.AI_GENERATION_LEASE_SECONDS,
    )


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


def clear_stop_request(message_id: int) -> None:
    runtime_store.delete(f"ai:message:{message_id}:stop")


def reset_for_tests() -> None:
    runtime_store.clear_prefix("ai:")
