"""登录防爆破：连续失败计数与账号锁定。

规则（可经 config 调整）：连续失败 ``LOGIN_MAX_FAILURES`` 次，锁定
``LOGIN_LOCK_MINUTES`` 分钟。计数与锁定状态存入带 TTL 的 KV 存储
（Redis 优先，否则进程内存兜底）。锁定窗口内即使密码正确也拒绝。
"""
from __future__ import annotations

from app.core.config import settings
from app.core.store import store

_FAIL_PREFIX = "login:fail:"
_LOCK_PREFIX = "login:lock:"


def _norm(username: str) -> str:
    return (username or "").strip().lower()


def lock_remaining_seconds(username: str) -> int:
    """返回该账号剩余锁定秒数；未锁定返回 0。"""
    key = _LOCK_PREFIX + _norm(username)
    if store.get(key) is None:
        return 0
    ttl = store.ttl(key)
    return ttl if ttl > 0 else 0


def record_failure(username: str) -> int:
    """记录一次登录失败，返回当前累计失败次数；达到上限则触发锁定。"""
    uname = _norm(username)
    window = settings.LOGIN_LOCK_MINUTES * 60
    count = store.incr(_FAIL_PREFIX + uname, ttl=window)
    if count >= settings.LOGIN_MAX_FAILURES:
        store.set(_LOCK_PREFIX + uname, "1", ttl=window)
    return count


def remaining_attempts(username: str) -> int:
    """返回锁定前剩余可试次数（≥0）。"""
    count = store.get(_FAIL_PREFIX + _norm(username))
    used = int(count) if count else 0
    return max(0, settings.LOGIN_MAX_FAILURES - used)


def clear(username: str) -> None:
    """登录成功后清除失败计数与锁定。"""
    uname = _norm(username)
    store.delete(_FAIL_PREFIX + uname)
    store.delete(_LOCK_PREFIX + uname)
