"""人民币金额小写 → 大写转换（零依赖，用于付款审批单）。

规则对齐财政部票据填写规范：整数按「万/亿」四位分节，节内/节间零合并，
末尾「整」字与「元/角/分」处理。示例：
    1002.5     → 人民币壹仟零贰元伍角整
    105000.03  → 人民币壹拾万伍仟元零叁分
    1000001    → 人民币壹佰万零壹元整
    100000000  → 人民币壹亿元整
"""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_SMALL = ["", "拾", "佰", "仟"]
_BIG = ["", "万", "亿", "兆"]


def _section_to_cn(sec: int) -> str:
    """转换一个 4 位分节（1-9999），节内连续零合并为单个「零」。sec==0 返回空串。"""
    if sec == 0:
        return ""
    s = ""
    zero = False
    pos = 0
    t = sec
    while t > 0:
        d = t % 10
        if d == 0:
            zero = True
        else:
            if zero and s:  # 仅当右侧已有非零位时才补零（末尾零不补）
                s = _DIGITS[0] + s
            zero = False
            s = _DIGITS[d] + _SMALL[pos] + s
        t //= 10
        pos += 1
    return s


def _int_to_cn(integer: int) -> str:
    """正整数转大写（不含「元」）。integer==0 返回空串。"""
    if integer == 0:
        return ""
    secs: list[int] = []
    n = integer
    while n > 0:
        secs.append(n % 10000)
        n //= 10000
    top = len(secs) - 1
    parts: list[str] = []
    for idx in range(top, -1, -1):
        sec = secs[idx]
        if sec == 0:
            parts.append(_DIGITS[0])  # 整节为零 → 占位「零」，后续合并
            continue
        sec_cn = _section_to_cn(sec)
        # 非最高节且本节 < 1000（即高位有零）→ 需补一个节间「零」
        if idx != top and sec < 1000:
            sec_cn = _DIGITS[0] + sec_cn
        parts.append(sec_cn + _BIG[idx])
    s = "".join(parts)
    s = re.sub(_DIGITS[0] + "+", _DIGITS[0], s)  # 合并连续零
    return s.strip(_DIGITS[0])


def amount_to_cn(value) -> str:
    """将金额（元）转为人民币大写。非法/负值返回空串。"""
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:  # noqa: BLE001
        return ""
    if amount < 0:
        return ""
    if amount == 0:
        return "人民币零元整"

    integer = int(amount)
    cents = int((amount - integer) * 100)
    jiao, fen = divmod(cents, 10)

    int_cn = _int_to_cn(integer)
    result = "人民币"
    if int_cn:
        result += int_cn + "元"

    if jiao == 0 and fen == 0:
        result += "整"
    else:
        if jiao:
            result += _DIGITS[jiao] + "角"
        elif int_cn:
            result += _DIGITS[0]  # 元与分之间补「零」
        if fen:
            result += _DIGITS[fen] + "分"
        else:
            result += "整"
    return result
