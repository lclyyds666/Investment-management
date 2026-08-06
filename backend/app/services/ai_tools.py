"""Static, permission-checked, aggregate-only tools for the AI assistant."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import CompanyCode, ResourceCode
from app.models.ai_assistant import AiToolCall
from app.models.user import User
from app.schemas.ai_assistant import (
    EmptyToolInput,
    NavigationInput,
    ScenicComparisonInput,
    ScenicNavigationAction,
    ScenicQueryInput,
    ScenicSummaryOut,
    ScenicTrendInput,
    ScenicTrendPointOut,
    ToolResult,
)
from app.services.ai_dates import DateRange, resolve_date_range
from app.services.permissions import has_resource
from app.services.portal import applications_for_user
from app.services.scenic_analytics import ScenicAnalyticsService
from app.services.scenic_config import get_effective_config, list_effective_configs


@dataclass(frozen=True)
class ToolContext:
    db: Session
    user: User
    request_id: str
    message_id: int | None = None


@dataclass(frozen=True)
class ToolSpec:
    input_model: type[BaseModel]
    handler: Callable[[BaseModel, ToolContext], ToolResult]
    scenic_permission: bool = False


def _overview(_: EmptyToolInput, __: ToolContext) -> ToolResult:
    return ToolResult(data={
        "product_name": settings.PROJECT_NAME,
        "purpose": "统一承载投资、供应链和基金管理业务，并提供统一身份、权限、流程、接口、运维和安全能力。",
        "applications": [
            {"code": "investment", "name": "山东出版投资有限公司", "status": "建设中"},
            {"code": "supplymanagement", "name": "山东出版供应链管理有限公司", "status": "已上线"},
            {"code": "fundmanagement", "name": "山东出版股权基金管理有限公司", "status": "建设中"},
        ],
    })


def _applications(_: EmptyToolInput, context: ToolContext) -> ToolResult:
    applications = [item.model_dump(mode="json") for item in applications_for_user(
        context.db, context.user
    )]
    return ToolResult(data={"applications": applications})


def _date_range(start: date, end: date) -> DateRange:
    value = resolve_date_range(f"{start.isoformat()}至{end.isoformat()}")
    if value is None:
        raise ValueError("无法识别查询日期")
    return value


def _summary(payload: ScenicQueryInput, context: ToolContext) -> ToolResult:
    values = ScenicAnalyticsService(context.db).summary(
        payload.scenic_ids, _date_range(payload.start_date, payload.end_date)
    )
    data = [ScenicSummaryOut.model_validate(value).model_dump(mode="json") for value in values]
    return ToolResult(data={"summaries": data}, metadata={"result_count": len(data)})


def _trend(payload: ScenicTrendInput, context: ToolContext) -> ToolResult:
    values = ScenicAnalyticsService(context.db).trend(
        payload.scenic_ids,
        _date_range(payload.start_date, payload.end_date),
        payload.dimension,
    )
    data = [ScenicTrendPointOut.model_validate(value).model_dump(mode="json") for value in values]
    return ToolResult(data={"points": data}, metadata={"result_count": len(data)})


def _compare(payload: ScenicComparisonInput, context: ToolContext) -> ToolResult:
    values = ScenicAnalyticsService(context.db).summary(
        payload.scenic_ids, _date_range(payload.start_date, payload.end_date)
    )
    data = [ScenicSummaryOut.model_validate(value).model_dump(mode="json") for value in values]
    return ToolResult(data={"comparisons": data}, metadata={"result_count": len(data)})


def _navigation(payload: NavigationInput, context: ToolContext) -> ToolResult:
    config = get_effective_config(context.db, payload.scenic_id)
    action = ScenicNavigationAction(
        scenic_id=payload.scenic_id,
        label=f"前往{config.scenic_name}",
    )
    return ToolResult(actions=[action], data={"scenic_id": payload.scenic_id})


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "get_platform_overview": ToolSpec(EmptyToolInput, _overview),
    "get_portal_applications": ToolSpec(EmptyToolInput, _applications),
    "get_scenic_summary": ToolSpec(ScenicQueryInput, _summary, scenic_permission=True),
    "get_scenic_trend": ToolSpec(ScenicTrendInput, _trend, scenic_permission=True),
    "compare_scenics": ToolSpec(ScenicComparisonInput, _compare, scenic_permission=True),
    "create_scenic_navigation_action": ToolSpec(
        NavigationInput, _navigation, scenic_permission=True
    ),
}


def _canonical_lookup(context: ToolContext) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for config in list_effective_configs(context.db):
        lookup[config.scenic_id.strip().casefold()] = config.scenic_id
        lookup[config.scenic_name.strip().casefold()] = config.scenic_id
    return lookup


def _canonicalize(payload: BaseModel, context: ToolContext) -> BaseModel:
    lookup = _canonical_lookup(context)
    if hasattr(payload, "scenic_ids"):
        canonical: list[str] = []
        for value in payload.scenic_ids:
            scenic_id = lookup.get(value.strip().casefold())
            if scenic_id is None:
                raise ValueError(f"未登记的景区：{value}")
            if scenic_id not in canonical:
                canonical.append(scenic_id)
        if isinstance(payload, ScenicComparisonInput) and len(canonical) < 2:
            raise ValueError("景区对比至少需要两个不同景区")
        return payload.model_copy(update={"scenic_ids": canonical})
    if hasattr(payload, "scenic_id"):
        scenic_id = lookup.get(payload.scenic_id.strip().casefold())
        if scenic_id is None:
            raise ValueError(f"未登记的景区：{payload.scenic_id}")
        return payload.model_copy(update={"scenic_id": scenic_id})
    return payload


def _result_summary(result: ToolResult) -> dict:
    items = (
        result.data.get("summaries")
        or result.data.get("comparisons")
        or result.data.get("points")
        or []
    )
    sales = sum((Decimal(str(item.get("sales", 0))) for item in items), Decimal("0"))
    return {
        "result_count": len(items),
        "sales_total": str(sales),
        "action_count": len(result.actions),
    }


def _record(
    context: ToolContext,
    name: str,
    payload: BaseModel,
    permission_decision: str,
    status: str,
    started: float,
    result: ToolResult | None = None,
) -> None:
    if context.message_id is None:
        return
    context.db.add(AiToolCall(
        message_id=context.message_id,
        tool_name=name,
        arguments_json=payload.model_dump(mode="json"),
        permission_decision=permission_decision,
        status=status,
        duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
        result_summary_json=_result_summary(result) if result else {},
    ))


def execute_tool(name: str, arguments: dict, context: ToolContext) -> ToolResult:
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        raise ValueError(f"未授权的工具：{name}")

    payload = spec.input_model.model_validate(arguments)
    started = time.perf_counter()
    if spec.scenic_permission and not has_resource(
        context.db,
        context.user,
        CompanyCode.SUPPLY_MANAGEMENT,
        ResourceCode.SCENIC_ANALYTICS,
    ):
        _record(context, name, payload, "denied", "failed", started)
        raise PermissionError("没有景区经营数据访问权限")

    try:
        if spec.scenic_permission:
            payload = _canonicalize(payload, context)
        result = spec.handler(payload, context)
    except Exception:
        _record(context, name, payload, "allowed", "failed", started)
        raise
    _record(context, name, payload, "allowed", "completed", started, result)
    return result
