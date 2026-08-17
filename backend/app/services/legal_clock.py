"""法务业务统一时区时钟。"""
from __future__ import annotations

from datetime import date, datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import settings


@lru_cache(maxsize=8)
def _zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def legal_now_aware(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(_zone(settings.LEGAL_ALERT_TIMEZONE))


def legal_now() -> datetime:
    """返回法务业务时区的无时区时间，兼容现有 MySQL DATETIME 列。"""
    return legal_now_aware().replace(tzinfo=None)


def legal_today() -> date:
    return legal_now_aware().date()
