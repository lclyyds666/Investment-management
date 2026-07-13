"""敏感数据脱敏工具（手机号 / 证件 / 银行卡等）。

用于列表等非必要展示明文的场景，满足合规「敏感数据保护」要求。
详情页如需明文，可绕过本工具直接返回（按角色控制）。
"""
from __future__ import annotations

import re

_DIGITS = re.compile(r"\d")


def mask_phone(value: str | None) -> str:
    """手机号脱敏：13812345678 → 138****5678。

    - 标准 11 位手机号：保留前 3 后 4，中间 4 位以 * 替换；
    - 座机 / 其他长度：保留前后各 1/4，中间打码，尽量不泄露；
    - 空值原样返回空串。
    """
    if not value:
        return ""
    s = str(value).strip()
    digits = _DIGITS.findall(s)
    if len(digits) == 11:
        return f"{s[:3]}****{s[-4:]}"
    if len(s) <= 4:
        return s[0] + "*" * (len(s) - 1) if len(s) > 1 else s
    head = max(1, len(s) // 4)
    tail = max(1, len(s) // 4)
    return s[:head] + "*" * (len(s) - head - tail) + s[-tail:]


def mask_id_card(value: str | None) -> str:
    """身份证脱敏：保留前 6 后 4。"""
    if not value:
        return ""
    s = str(value).strip()
    if len(s) < 8:
        return "*" * len(s)
    return s[:6] + "*" * (len(s) - 10) + s[-4:]
