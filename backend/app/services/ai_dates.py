"""Resolve supported Chinese date expressions in the Asia/Shanghai timezone."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date
    label: str


_CHINESE_NUMBERS = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "二十四": 24, "三十六": 36,
}


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _month_end(value: date) -> date:
    return _add_months(_month_start(value), 1) - timedelta(days=1)


def _number(value: str) -> int:
    if value.isdigit():
        return int(value)
    if value in _CHINESE_NUMBERS:
        return _CHINESE_NUMBERS[value]
    if value.startswith("十") and len(value) == 2:
        return 10 + _CHINESE_NUMBERS.get(value[1], 0)
    if value.endswith("十") and len(value) == 2:
        return _CHINESE_NUMBERS.get(value[0], 0) * 10
    if "十" in value and len(value) == 3:
        return _CHINESE_NUMBERS.get(value[0], 0) * 10 + _CHINESE_NUMBERS.get(value[2], 0)
    raise ValueError("无法识别月份数量")


def _validated(start: date, end: date) -> DateRange:
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    if end >= _add_months(start, settings.AI_MAX_QUERY_MONTHS):
        raise ValueError(f"查询范围不能超过 {settings.AI_MAX_QUERY_MONTHS} 个月")
    return DateRange(start=start, end=end, label=f"{start.isoformat()} 至 {end.isoformat()}")


def _parse_date(value: str) -> date:
    year, month, day = (int(part) for part in value.split("-"))
    return date(year, month, day)


def resolve_date_range(text: str, now: datetime | None = None) -> DateRange | None:
    value = re.sub(r"\s+", "", text or "")
    current = now or datetime.now(SHANGHAI)
    if current.tzinfo is None:
        current = current.replace(tzinfo=SHANGHAI)
    else:
        current = current.astimezone(SHANGHAI)
    today = current.date()

    explicit = re.search(r"(20\d{2}-\d{1,2}-\d{1,2})(?:至|到|~|—|-)(20\d{2}-\d{1,2}-\d{1,2})", value)
    if explicit:
        return _validated(_parse_date(explicit.group(1)), _parse_date(explicit.group(2)))

    if "上个月" in value or "上月" in value:
        start = _add_months(_month_start(today), -1)
        return _validated(start, _month_end(start))
    if "本月" in value or "这个月" in value:
        return _validated(_month_start(today), today)
    if "去年" in value:
        return _validated(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))
    if "今年" in value:
        return _validated(date(today.year, 1, 1), today)

    recent = re.search(r"(?:最近|近)([一二两三四五六七八九十\d]+)个月", value)
    if recent:
        count = _number(recent.group(1))
        if count < 1 or count > settings.AI_MAX_QUERY_MONTHS:
            raise ValueError(f"查询范围不能超过 {settings.AI_MAX_QUERY_MONTHS} 个月")
        return _validated(_add_months(_month_start(today), -(count - 1)), today)

    month_match = re.search(r"(20\d{2})年(\d{1,2})月", value)
    if month_match:
        start = date(int(month_match.group(1)), int(month_match.group(2)), 1)
        return _validated(start, _month_end(start))

    quarter = re.search(r"(20\d{2})年第?([1-4一二三四])季度", value)
    if quarter:
        number = _number(quarter.group(2))
        start = date(int(quarter.group(1)), (number - 1) * 3 + 1, 1)
        return _validated(start, _month_end(_add_months(start, 2)))

    year_match = re.search(r"(20\d{2})年", value)
    if year_match:
        year = int(year_match.group(1))
        return _validated(date(year, 1, 1), date(year, 12, 31))

    return None
