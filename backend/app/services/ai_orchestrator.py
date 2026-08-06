"""Local-first AI intent routing, aggregate tools, streaming, and fallbacks."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

from app.core.config import settings
from app.schemas.ai_assistant import ToolResult
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

    async def stream(
        self, question: str, context: ToolContext
    ) -> AsyncIterator[OrchestratorEvent]:
        decision = await self._decision(question)
        request = _tool_request(decision)
        if request is None:
            try:
                emitted = False
                async for chunk in self._stream_model(_FREE_SYSTEM_PROMPT, question):
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
        yield OrchestratorEvent("tool.status", {"tool": tool_name, "status": "completed"})

        data = _tool_data(result)
        model_context = json.dumps(
            {"intent": decision.intent, "aggregate_result": data},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        used_model = False
        try:
            async for chunk in self._stream_model(_DATA_SYSTEM_PROMPT, model_context):
                used_model = True
                yield OrchestratorEvent("text.delta", {"text": chunk, "engine": "deepseek"})
            if not used_model:
                raise RuntimeError("empty model response")
            metadata = _metadata_lines(data)
            if metadata:
                yield OrchestratorEvent("text.delta", {
                    "text": "\n\n" + "\n".join(metadata), "engine": "local",
                })
        except Exception:
            yield OrchestratorEvent("text.delta", {
                "text": _fallback(decision.intent, data), "engine": "local",
            })

        for action in _actions(result):
            yield OrchestratorEvent("action", action)
