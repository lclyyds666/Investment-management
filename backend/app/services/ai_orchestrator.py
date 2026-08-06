"""Local-first AI intent routing, aggregate tools, streaming, and fallbacks."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

from app.core.config import settings
from app.schemas.ai_assistant import ToolResult
from app.services.ai_dates import resolve_date_range
from app.services.ai_tools import ToolContext, execute_tool
from app.services.deepseek_chat import DeepSeekChatClient, IntentDecision
from app.services.scenic_config import SCENIC_SEEDS, list_effective_configs


_UNAVAILABLE = "AI 服务暂时不可用，请稍后重试。"


@dataclass(frozen=True)
class OrchestratorEvent:
    kind: Literal["tool.status", "text.delta", "action", "error"]
    payload: dict[str, Any]


LOCAL_ENGINE = "local"


_URL_RE = re.compile(
    r"(?:(?:https?|ftp):?//|//[a-z0-9-]|www\.|(?:[a-z0-9-]+\.)+[a-z]{2,63}\b)",
    re.IGNORECASE,
)
_SQL_RE = re.compile(
    r"(?:select.*from|insertinto|update[a-z_]*set|deletefrom|drop(?:table|database)|"
    r"altertable|createtable|truncate(?:table)?|unionselect|show(?:tables|columns)|"
    r"describe[a-z_]*|pragma(?:table_info)?|with[a-z_]+as\(|call[a-z_]+\(|exec(?:ute)?[a-z_]+)",
    re.IGNORECASE,
)
_FORMULA_RE = re.compile(
    r"(?:[=+*/\u00d7\u00f7]|(?:sum|avg|count|round|if)\(|formula|calculatedas|"
    r"dividedby|multipliedby|\u516c\u5f0f|\u8ba1\u7b97\u89c4\u5219|\u9664\u4ee5|\u4e58\u4ee5|\u52a0\u4e0a|\u51cf\u53bb)",
    re.IGNORECASE,
)
_CREDENTIAL_RE = re.compile(
    r"(?:api(?:key)?|access(?:token)?|secret|password|passwd|authorization|bearer|"
    r"token|sk-[a-z0-9_-]+|gh[oprsu]_[a-z0-9_]+|akia[a-z0-9]+|"
    r"eyj[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+|\u5bc6\u7801|\u5bc6\u94a5|\u4ee4\u724c|\u51ed\u8bc1)",
    re.IGNORECASE,
)
_DATABASE_RE = re.compile(
    r"(?:database|schema|table|column|information_schema|mysql|postgres(?:ql)?|sqlite|"
    r"\u6570\u636e\u5e93|\u6570\u636e\u8868|\u5b57\u6bb5|\u8868\u7ed3\u6784|\u5e93\u8868)",
    re.IGNORECASE,
)
_RAW_CONTENT_RE = re.compile(
    r"(?:daily_json|source_file|ticket_ledger|hotel_ledger|biz_[a-z0-9_]+|"
    r"raw_?ledger|attachment|upload(?:ed)?_file|\u539f\u59cb\u53f0\u8d26|"
    r"\u53f0\u8d26(?:\u660e\u7ec6|\u884c|\u8bb0\u5f55)|\u5bf9\u8d26\u660e\u7ec6|"
    r"\u9644\u4ef6(?:\u5185\u5bb9|\u539f\u6587|\u6587\u4ef6))",
    re.IGNORECASE,
)
_RAW_ROW_RE = re.compile(
    r"\{(?:\"?[a-z_][a-z0-9_]*\"?:[^,{}]+,){1,}\"?[a-z_][a-z0-9_]*\"?:",
    re.IGNORECASE,
)
_SCENIC_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def _normalized_output(text: str) -> tuple[str, str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = "".join(
        char for char in normalized
        if not unicodedata.category(char).startswith("C") or char in "\n\r\t"
    )
    return normalized, re.sub(r"\s+", "", normalized)


def is_safe_model_text(text: str) -> bool:
    """Return whether provider text contains no forbidden content."""
    if not text:
        return False
    normalized, compact = _normalized_output(text)
    return not (
        _URL_RE.search(compact)
        or _SQL_RE.search(compact)
        or _FORMULA_RE.search(compact)
        or _CREDENTIAL_RE.search(compact)
        or _DATABASE_RE.search(normalized)
        or _RAW_CONTENT_RE.search(normalized)
        or _RAW_ROW_RE.search(compact)
    )


def _db_from_context(context: Any) -> Any:
    return getattr(context, "db", context)


def _is_safe_scenic_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_SCENIC_ID_RE.fullmatch(value))


def _seed_registry() -> list[dict[str, str]]:
    return [
        {"scenic_id": item[0], "scenic_name": item[1]}
        for item in SCENIC_SEEDS
        if _is_safe_scenic_id(item[0])
    ]


def _effective_registry(context: Any) -> list[dict[str, str]]:
    """Return route-safe configs; only explicit standalone use falls back to seeds."""
    if context is None:
        return _seed_registry()
    try:
        configs = list_effective_configs(_db_from_context(context))
        registry = []
        for config in configs:
            scenic_id = (
                config.get("scenic_id")
                if isinstance(config, dict)
                else getattr(config, "scenic_id", None)
            )
            scenic_name = (
                config.get("scenic_name")
                if isinstance(config, dict)
                else getattr(config, "scenic_name", None)
            )
            if (
                _is_safe_scenic_id(scenic_id)
                and isinstance(scenic_name, str)
                and scenic_name.strip()
            ):
                registry.append({"scenic_id": scenic_id, "scenic_name": scenic_name})
        return registry
    except Exception:  # noqa: BLE001 - contextual registry resolution fails closed
        return []


def _allowed_scenics(context: Any = None) -> list[dict[str, str]]:
    return _effective_registry(context)


def _local_intent(question: str, context: Any = None) -> IntentDecision | None:
    normalized = "".join((question or "").casefold().split())
    scenic_ids = []
    for item in _effective_registry(context):
        scenic_id = item["scenic_id"]
        scenic_name = item["scenic_name"]
        scenic_key = "".join(scenic_id.casefold().split())
        scenic_name_key = "".join(scenic_name.casefold().split())
        if scenic_key in normalized or scenic_name_key in normalized:
            scenic_ids.append(scenic_id)

    if scenic_ids:
        if any(word in normalized for word in ("打开", "前往", "跳转", "进入", "带我去")):
            return IntentDecision(intent="scenic_navigation", scenic_ids=scenic_ids[:1])
        if len(scenic_ids) > 1 or any(word in normalized for word in ("对比", "比较", "哪个")):
            return IntentDecision(
                intent="compare_scenics", scenic_ids=scenic_ids, date_text=question
            )
        if any(word in normalized for word in ("趋势", "走势", "按月", "变化")):
            dimension = "platform" if "平台" in normalized else "month"
            return IntentDecision(
                intent="scenic_trend", scenic_ids=scenic_ids,
                date_text=question, dimension=dimension,
            )
        return IntentDecision(
            intent="scenic_summary", scenic_ids=scenic_ids, date_text=question
        )

    if any(word in normalized for word in (
        "三个业务系统", "业务系统", "建设情况", "投资公司", "基金公司",
        "供应链公司", "investment", "fundmanagement", "supplymanagement",
    )) or (
        any(word in normalized for word in ("投资", "基金", "供应链"))
        and any(word in normalized for word in ("数据", "业务", "系统", "情况"))
    ):
        return IntentDecision(intent="portal_applications")
    if any(word in normalized for word in (
        "平台是干什么", "这个平台", "介绍平台", "平台介绍", "工作平台",
    )):
        return IntentDecision(intent="platform_overview")
    return None


def _validate_decision(decision: IntentDecision, context: Any = None) -> IntentDecision:
    lookup: dict[str, str] = {}
    for item in _effective_registry(context):
        lookup[item["scenic_id"].casefold()] = item["scenic_id"]
        lookup[item["scenic_name"].strip().casefold()] = item["scenic_id"]
    canonical_ids: list[str] = []
    for scenic_id in decision.scenic_ids:
        if not isinstance(scenic_id, str):
            return IntentDecision(intent="free_form")
        canonical_id = lookup.get(scenic_id.strip().casefold())
        if canonical_id is None:
            return IntentDecision(intent="free_form")
        if canonical_id not in canonical_ids:
            canonical_ids.append(canonical_id)
    decision = decision.model_copy(update={"scenic_ids": canonical_ids})
    if decision.intent.startswith("scenic") or decision.intent == "compare_scenics":
        if not decision.scenic_ids:
            return IntentDecision(intent="free_form")
    return decision


def _tool_request(decision: IntentDecision) -> tuple[str, dict] | None:
    if decision.intent == "platform_overview":
        return "get_platform_overview", {}
    if decision.intent == "portal_applications":
        return "get_portal_applications", {}
    if decision.intent == "scenic_navigation":
        return "create_scenic_navigation_action", {"scenic_id": decision.scenic_ids[0]}
    if decision.intent in {"scenic_summary", "scenic_trend", "compare_scenics"}:
        date_range = resolve_date_range(decision.date_text or "")
        if date_range is None:
            date_range = resolve_date_range("今年")
        arguments: dict[str, Any] = {
            "scenic_ids": decision.scenic_ids,
            "start_date": date_range.start.isoformat(),
            "end_date": date_range.end.isoformat(),
        }
        if decision.intent == "scenic_trend":
            arguments["dimension"] = decision.dimension or "month"
            return "get_scenic_trend", arguments
        if decision.intent == "compare_scenics":
            return "compare_scenics", arguments
        return "get_scenic_summary", arguments
    return None


def _tool_data(result: Any) -> dict:
    if isinstance(result, ToolResult):
        return result.model_dump(mode="json")["data"]
    return getattr(result, "data", {}) or {}


def _actions(result: Any) -> list[dict]:
    actions = getattr(result, "actions", []) or []
    safe_actions = []
    for action in actions:
        payload = (
            action.model_dump(mode="json")
            if hasattr(action, "model_dump")
            else dict(action)
        )
        if _is_safe_scenic_id(payload.get("scenic_id")):
            safe_actions.append(payload)
    return safe_actions


def _metadata_lines(data: dict) -> list[str]:
    items = data.get("summaries") or data.get("comparisons") or data.get("points") or []
    lines: list[str] = []
    seen: set[tuple] = set()
    for item in items:
        key = (
            item.get("scenic_id"), item.get("requested_start"), item.get("requested_end"),
            item.get("covered_start"), item.get("covered_end"), item.get("data_updated_at"),
        )
        if key in seen:
            continue
        seen.add(key)
        covered = (
            f"{item.get('covered_start')} 至 {item.get('covered_end')}"
            if item.get("covered_start") and item.get("covered_end") else "暂无有效数据"
        )
        updated = item.get("data_updated_at") or "暂无更新时间"
        coverage = "部分覆盖" if item.get("partial_coverage") else "完整覆盖"
        lines.append(
            f"{item.get('scenic_name') or item.get('scenic_id')}：请求范围 "
            f"{item.get('requested_start')} 至 {item.get('requested_end')}；"
            f"实际覆盖 {covered}（{coverage}）；数据更新时间 {updated}。"
        )
    return lines


def _stream_metadata(data: dict) -> dict[str, str]:
    items = data.get("summaries") or data.get("comparisons") or data.get("points") or []
    if not items:
        return {}

    def values(key: str) -> list[str]:
        return [str(item[key]) for item in items if item.get(key)]

    requested_starts = values("requested_start")
    requested_ends = values("requested_end")
    covered_starts = values("covered_start")
    covered_ends = values("covered_end")
    updated_values = values("data_updated_at")
    metadata: dict[str, str] = {}
    if requested_starts:
        metadata["data_start_date"] = min(requested_starts)
    if requested_ends:
        metadata["data_end_date"] = max(requested_ends)
    if covered_starts:
        metadata["data_covered_start"] = min(covered_starts)
    if covered_ends:
        metadata["data_covered_end"] = max(covered_ends)
    if updated_values:
        metadata["data_updated_at"] = max(updated_values)
    return metadata


def _fallback(intent: str, data: dict) -> str:
    if intent == "platform_overview":
        return (
            f"{settings.PROJECT_NAME}用于统一承载投资、供应链和基金管理业务。"
            "目前供应链管理系统已上线，投资管理和股权基金管理门户正在建设中；"
            "平台统一身份、权限、流程、接口、运维和安全能力。"
        )
    if intent == "portal_applications":
        return (
            "当前有三个业务入口：山东出版投资有限公司和山东出版股权基金管理有限公司"
            "处于建设中，暂无可查询业务数据；山东出版供应链管理有限公司系统已上线。"
        )
    if intent == "scenic_navigation":
        return "已准备好景区入口，请点击下方操作按钮前往。"

    items = data.get("summaries") or data.get("comparisons") or data.get("points") or []
    if not items:
        return "所选范围内暂无可用的景区聚合数据。"
    lines = []
    for item in items:
        name = item.get("scenic_name") or item.get("scenic_id")
        lines.append(
            f"{name}销售额 {item.get('sales', '0')} 元，核销数 "
            f"{item.get('writeoff_count', 0)}，核销率 {item.get('writeoff_rate', '0')}%。"
        )
    metadata = _metadata_lines(data)
    return "\n".join([*lines, *metadata])


class AiOrchestrator:
    def __init__(self, client: DeepSeekChatClient | None = None):
        self.client = client or DeepSeekChatClient()

    async def _decision(self, question: str, context: Any = None) -> IntentDecision:
        local = _local_intent(question, context)
        if local is not None:
            return _validate_decision(local, context)
        try:
            return _validate_decision(
                await self.client.classify(question, _allowed_scenics(context)), context
            )
        except Exception:
            return IntentDecision(intent="free_form")

    async def stream(
        self, question: str, context: ToolContext
    ) -> AsyncIterator[OrchestratorEvent]:
        decision = await self._decision(question, context)
        request = _tool_request(decision)
        if request is None:
            yield OrchestratorEvent(
                "text.delta", {"text": _UNAVAILABLE, "engine": LOCAL_ENGINE}
            )
            return

        tool_name, arguments = request
        yield OrchestratorEvent("tool.status", {"tool": tool_name, "status": "running"})
        try:
            result = execute_tool(tool_name, arguments, context)
        except PermissionError:
            yield OrchestratorEvent("error", {
                "code": "forbidden", "message": "没有景区经营数据访问权限",
            })
            return
        except Exception:
            yield OrchestratorEvent("error", {
                "code": "tool_failed", "message": "暂时无法获取所需数据",
            })
            return
        data = _tool_data(result)
        yield OrchestratorEvent("tool.status", {
            "tool": tool_name,
            "status": "completed",
            "metadata": _stream_metadata(data),
        })
        yield OrchestratorEvent("text.delta", {
            "text": _fallback(decision.intent, data), "engine": LOCAL_ENGINE,
        })

        for action in _actions(result):
            yield OrchestratorEvent("action", action)
