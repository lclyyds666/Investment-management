"""Local-first AI intent routing, aggregate tools, streaming, and fallbacks."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

from app.core.config import settings
from app.schemas.ai_assistant import ToolResult
from app.services import ai_runtime
from app.services.ai_dates import resolve_date_range
from app.services.ai_tools import ToolContext, execute_tool
from app.services.deepseek_chat import DeepSeekChatClient, IntentDecision
from app.services.scenic_config import SCENIC_SEEDS


_UNAVAILABLE = "AI 服务暂时不可用，请稍后重试。"
_DATA_SYSTEM_PROMPT = (
    "你是山东出版投资有限公司工作平台的只读 AI 助手。"
    "仅根据提供的聚合 JSON 作答，不得推测缺失数据，不得输出内部公式、SQL、字段名、"
    "原始台账、附件、凭据、任意链接或修改操作。语言简洁、专业。"
)
_FREE_SYSTEM_PROMPT = (
    "你是山东出版投资有限公司工作平台的 AI 助手。不得披露或猜测凭据、数据库结构、"
    "SQL、内部计算公式或原始业务数据，不得生成可执行的业务写操作。"
)


@dataclass(frozen=True)
class OrchestratorEvent:
    kind: Literal["tool.status", "text.delta", "action", "error"]
    payload: dict[str, Any]


class ModelOutputRejected(RuntimeError):
    """Raised when provider output cannot be safely shown or persisted."""


_COMPLETE_SEGMENT_RE = re.compile(r"[\u3002\uff01\uff1f!?]+(?:[\"'\u201d\u2019\uff09\u3011]*)|(?:\r?\n)+")
_URL_RE = re.compile(r"(?:(?:https?|ftp)://|www\.)", re.IGNORECASE)
_SQL_RE = re.compile(
    r"(?:select.*from|insertinto|update[a-z_]*set|deletefrom|drop(?:table|database)|"
    r"altertable|createtable|truncate(?:table)?|unionselect|show(?:tables|columns)|"
    r"describe[a-z_]*)",
    re.IGNORECASE,
)
_FORMULA_RE = re.compile(
    r"(?:[=+*/\u00d7\u00f7]|(?:sum|avg|count|round|if)\(|\u516c\u5f0f|\u8ba1\u7b97\u89c4\u5219)",
    re.IGNORECASE,
)
_CREDENTIAL_RE = re.compile(
    r"(?:api(?:key)?|access(?:token)?|secret|password|passwd|authorization|bearer|"
    r"token|sk-[a-z0-9_-]+|akia[a-z0-9]+|\u5bc6\u7801|\u5bc6\u94a5|\u4ee4\u724c|\u51ed\u8bc1)",
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
_MAX_PENDING_MODEL_CHARS = 4096


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
    )


def is_safe_model_segment(text: str) -> bool:
    """Return whether a complete provider segment is safe for display and storage."""
    boundaries = list(_COMPLETE_SEGMENT_RE.finditer(text))
    return bool(boundaries and boundaries[-1].end() == len(text) and is_safe_model_text(text))


def _allowed_scenics() -> list[dict[str, str]]:
    return [{"scenic_id": item[0], "scenic_name": item[1]} for item in SCENIC_SEEDS]


def _local_intent(question: str) -> IntentDecision | None:
    normalized = "".join((question or "").lower().split())
    scenic_ids = [
        item[0] for item in SCENIC_SEEDS
        if item[0].lower() in normalized or item[1].lower() in normalized
    ]

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


def _validate_decision(decision: IntentDecision) -> IntentDecision:
    allowed = {item[0] for item in SCENIC_SEEDS}
    if any(scenic_id not in allowed for scenic_id in decision.scenic_ids):
        return IntentDecision(intent="free_form")
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
    return [
        action.model_dump(mode="json") if hasattr(action, "model_dump") else dict(action)
        for action in actions
    ]


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

    async def _decision(self, question: str) -> IntentDecision:
        local = _local_intent(question)
        if local is not None:
            return local
        try:
            return _validate_decision(await self.client.classify(question, _allowed_scenics()))
        except Exception:
            return IntentDecision(intent="free_form")

    async def _stream_model(self, prompt: str, context: str) -> AsyncIterator[str]:
        async for chunk in self.client.stream_answer(prompt, context):
            if chunk:
                yield chunk

    async def _safe_model_segments(
        self, prompt: str, context: str, message_id: int | None
    ) -> AsyncIterator[str]:
        pending = ""
        async for chunk in self._stream_model(prompt, context):
            if message_id is not None and ai_runtime.is_stop_requested(message_id):
                return
            pending += chunk
            if len(pending) > _MAX_PENDING_MODEL_CHARS:
                raise ModelOutputRejected("model output did not reach a safe boundary")
            while match := _COMPLETE_SEGMENT_RE.search(pending):
                segment = pending[:match.end()]
                pending = pending[match.end():]
                if not is_safe_model_segment(segment):
                    raise ModelOutputRejected("model output violates the output policy")
                yield segment
        if pending.strip():
            raise ModelOutputRejected("model output ended without a complete segment")

    @staticmethod
    def _message_id(context: ToolContext) -> int | None:
        message_id = getattr(context, "message_id", None)
        return message_id if isinstance(message_id, int) else None

    async def stream(
        self, question: str, context: ToolContext
    ) -> AsyncIterator[OrchestratorEvent]:
        decision = await self._decision(question)
        request = _tool_request(decision)
        if request is None:
            try:
                emitted = False
                async for chunk in self._safe_model_segments(
                    _FREE_SYSTEM_PROMPT, question, self._message_id(context)
                ):
                    emitted = True
                    yield OrchestratorEvent("text.delta", {"text": chunk, "engine": "deepseek"})
                if not emitted:
                    raise RuntimeError("empty model response")
            except Exception:
                yield OrchestratorEvent("text.delta", {"text": _UNAVAILABLE, "engine": "local"})
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
        model_context = json.dumps(
            {"intent": decision.intent, "aggregate_result": data},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        used_model = False
        try:
            async for chunk in self._safe_model_segments(
                _DATA_SYSTEM_PROMPT, model_context, self._message_id(context)
            ):
                used_model = True
                yield OrchestratorEvent("text.delta", {"text": chunk, "engine": "deepseek"})
            if not used_model:
                raise RuntimeError("empty model response")
            metadata = _metadata_lines(data)
            if metadata:
                yield OrchestratorEvent("text.delta", {
                    "text": "\n\n" + "\n".join(metadata), "engine": "local",
                })
        except ModelOutputRejected:
            yield OrchestratorEvent("text.delta", {
                "text": _UNAVAILABLE, "engine": "local",
            })
        except Exception:
            yield OrchestratorEvent("text.delta", {
                "text": _fallback(decision.intent, data), "engine": "local",
            })

        for action in _actions(result):
            yield OrchestratorEvent("action", action)
