"""图形验证码：生成与校验。

采用 SVG 矢量绘制（对齐项目内 Mock 电子签名的 SVG 方案），**零额外依赖**、
任意浏览器可直接渲染。验证码答案存入带 TTL 的 KV 存储（Redis 或内存兜底），
以一次性 captcha_id 关联，校验通过即失效，防止重放。
"""
from __future__ import annotations

import base64
import secrets

from app.core.config import settings
from app.core.store import store

# 去除易混淆字符（0/O、1/I/L、2/Z 等），提升人眼可读性
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_LEN = 4
_KEY_PREFIX = "captcha:"

# 深色主题下清晰可辨的字符配色
_COLORS = ["#22d3ee", "#1c9be6", "#7fd8ff", "#5ad1b0", "#f6c667", "#ff8fab"]


def _rand(seq):
    return seq[secrets.randbelow(len(seq))]


def _render_svg(code: str) -> str:
    width, height = 120, 44
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" rx="6" fill="#06142e"/>',
    ]
    # 干扰线
    for _ in range(4):
        x1, y1 = secrets.randbelow(width), secrets.randbelow(height)
        x2, y2 = secrets.randbelow(width), secrets.randbelow(height)
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{_rand(_COLORS)}" stroke-width="1" opacity="0.35"/>'
        )
    # 字符（随机颜色 + 轻微旋转）
    step = width / (_LEN + 1)
    for i, ch in enumerate(code):
        x = step * (i + 1) - 6
        y = 30 + secrets.randbelow(6)
        angle = secrets.randbelow(31) - 15  # -15° ~ +15°
        parts.append(
            f'<text x="{x:.0f}" y="{y}" font-family="Consolas,Menlo,monospace" '
            f'font-size="26" font-weight="700" fill="{_rand(_COLORS)}" '
            f'transform="rotate({angle} {x:.0f} {y})">{ch}</text>'
        )
    # 干扰点
    for _ in range(18):
        cx, cy = secrets.randbelow(width), secrets.randbelow(height)
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="1" fill="{_rand(_COLORS)}" opacity="0.4"/>')
    parts.append("</svg>")
    return "".join(parts)


def generate() -> tuple[str, str]:
    """生成一枚验证码，返回 (captcha_id, svg_data_uri)。答案已写入存储。"""
    code = "".join(_rand(_ALPHABET) for _ in range(_LEN))
    captcha_id = secrets.token_urlsafe(16)
    store.set(_KEY_PREFIX + captcha_id, code.lower(), ttl=settings.CAPTCHA_TTL_SECONDS)

    svg = _render_svg(code)
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return captcha_id, f"data:image/svg+xml;base64,{b64}"


def verify(captcha_id: str | None, code: str | None) -> bool:
    """校验验证码；成功即消费（删除），不区分大小写。"""
    if not captcha_id or not code:
        return False
    key = _KEY_PREFIX + captcha_id
    answer = store.get(key)
    if answer is None:
        return False
    store.delete(key)  # 一次性使用，无论对错都失效，避免暴力猜解
    return str(code).strip().lower() == answer
