"""钉钉法务预警群机器人适配器。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from app.core.config import settings
from app.models.legal_risk import LegalCase, LegalCaseAlert
from app.models.user import User
from app.services.legal_clock import legal_today


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    status: str
    response_summary: str = ""
    failure_reason: str = ""


def sign_webhook(secret: str, timestamp_ms: int) -> str:
    raw = f"{timestamp_ms}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return quote_plus(base64.b64encode(digest).decode("ascii"))


def signed_webhook_url(webhook: str, secret: str, timestamp_ms: int) -> str:
    separator = "&" if "?" in webhook else "?"
    return f"{webhook}{separator}timestamp={timestamp_ms}&sign={sign_webhook(secret, timestamp_ms)}"


def build_alert_message(
    alert: LegalCaseAlert,
    case: LegalCase,
    *,
    today: date | None = None,
    responsible_name: str = "",
) -> str:
    current = today or legal_today()
    days = (alert.due_date - current).days
    timing = f"剩余 {days} 天" if days >= 0 else f"逾期 {abs(days)} 天"
    type_labels = {
        "asset_expiry": "查冻扣到期",
        "enforcement_application": "申请执行",
        "hearing": "开庭提醒",
        "payment_material": "缴费/材料期限",
        "custom": "其他期限",
        "terminal_monitoring": "终本持续监控",
    }
    alert_type = alert.alert_type.value if hasattr(alert.alert_type, "value") else str(alert.alert_type)
    lines = [
        "【法务风控预警】",
        f"案件编号：{case.case_no or '-'}",
        f"预警类型：{type_labels.get(alert_type, alert_type)}",
        f"截止日期：{alert.due_date.isoformat()}",
        f"时限状态：{timing}",
    ]
    if responsible_name:
        lines.append(f"责任人：{responsible_name}")
    lines.append("请登录系统查看详情并及时处理。")
    return "\n".join(lines)


class DingTalkClient:
    def __init__(self, *, enabled=None, webhook=None, secret=None, timeout: float = 8.0):
        self.enabled = settings.DINGTALK_LEGAL_ALERT_ENABLED if enabled is None else enabled
        self.webhook = settings.DINGTALK_LEGAL_ALERT_WEBHOOK if webhook is None else webhook
        self.secret = settings.DINGTALK_LEGAL_ALERT_SECRET if secret is None else secret
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.webhook.strip())

    def send_alert(self, alert: LegalCaseAlert, case: LegalCase, responsible_user: User | None) -> DeliveryResult:
        at_mobiles = []
        if (
            responsible_user is not None
            and responsible_user.legal_alert_enabled
            and responsible_user.mobile
        ):
            at_mobiles.append(responsible_user.mobile)
        responsible_name = ""
        if responsible_user is not None:
            responsible_name = responsible_user.full_name or responsible_user.username
        return self._send(
            build_alert_message(alert, case, responsible_name=responsible_name),
            at_mobiles,
        )

    def send_test(self, actor_name: str) -> DeliveryResult:
        return self._send(f"【法务风控测试消息】\n操作人：{actor_name}\n钉钉机器人配置正常。", [])

    def _send(self, content: str, at_mobiles: list[str]) -> DeliveryResult:
        if not self.configured:
            return DeliveryResult(False, "channel_unconfigured", failure_reason="钉钉法务预警渠道未配置")
        timestamp_ms = int(time.time() * 1000)
        url = signed_webhook_url(self.webhook, self.secret, timestamp_ms) if self.secret else self.webhook
        body = json.dumps({
            "msgtype": "text",
            "text": {"content": content},
            "at": {"atMobiles": at_mobiles, "isAtAll": False},
        }, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - configured webhook
                raw = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw or "{}")
            if payload.get("errcode") == 0:
                return DeliveryResult(True, "sent", response_summary="ok")
            return DeliveryResult(False, "failed", response_summary=raw[:500],
                                  failure_reason=payload.get("errmsg") or "钉钉返回失败")
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return DeliveryResult(False, "failed", failure_reason=str(exc)[:1000])
