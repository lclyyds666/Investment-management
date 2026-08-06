"""Strict public contracts for the AI assistant."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictAiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ScenicNavigationAction(StrictAiModel):
    type: Literal["navigate_to_scenic"] = "navigate_to_scenic"
    scenic_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    label: str = Field(min_length=1, max_length=80)


class AiConversationCreate(StrictAiModel):
    title: str = Field(default="新会话", min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def title_must_contain_visible_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("会话标题不能为空")
        return value


class AiConversationUpdate(StrictAiModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def title_must_contain_visible_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("会话标题不能为空")
        return value


class AiMessageCreate(StrictAiModel):
    content: str = Field(min_length=1, max_length=2000)
    client_message_id: UUID

    @field_validator("content")
    @classmethod
    def content_must_contain_visible_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("消息内容不能为空")
        return value


class AiMessageOut(StrictAiModel):
    id: int
    conversation_id: int
    role: Literal["user", "assistant"]
    content: str
    status: Literal["generating", "completed", "stopped", "failed"]
    client_message_id: str | None = None
    request_id: str | None = None
    actions_json: list[ScenicNavigationAction] = Field(default_factory=list)
    data_start_date: date | None = None
    data_end_date: date | None = None
    data_covered_start: date | None = None
    data_covered_end: date | None = None
    data_updated_at: datetime | None = None
    engine: str | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime


class AiConversationOut(StrictAiModel):
    id: int
    owner_id: int
    title: str
    status: Literal["active"]
    last_active_at: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    messages: list[AiMessageOut] = Field(default_factory=list)


class AiConversationSummaryOut(StrictAiModel):
    id: int
    owner_id: int
    title: str
    status: Literal["active"]
    last_active_at: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class AiToolCallOut(StrictAiModel):
    id: int
    message_id: int
    tool_name: str
    arguments_json: dict[str, Any]
    permission_decision: Literal["allowed", "denied"]
    status: Literal["completed", "failed"]
    duration_ms: int | None = None
    result_summary_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AdminAiMessageOut(AiMessageOut):
    first_token_ms: int | None = None
    duration_ms: int | None = None
    tool_calls: list[AiToolCallOut] = Field(default_factory=list)


class AdminAiConversationOut(AiConversationSummaryOut):
    messages: list[AdminAiMessageOut] = Field(default_factory=list)


class ToolResult(StrictAiModel):
    data: dict[str, Any] = Field(default_factory=dict)
    actions: list[ScenicNavigationAction] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenicSummaryOut(StrictAiModel):
    scenic_id: str
    scenic_name: str
    requested_start: date
    requested_end: date
    covered_start: date | None = None
    covered_end: date | None = None
    data_updated_at: datetime | None = None
    partial_coverage: bool
    sales: Decimal
    writeoff_count: int
    positive_count: int
    writeoff_rate: Decimal
    existing_scale: Decimal
    realized_scale: Decimal
    gross_profit: Decimal
    capital_occupation_days: float | None = None
    ticket_total: Decimal
    hotel_total: Decimal


class ScenicTrendPointOut(StrictAiModel):
    scenic_id: str
    scenic_name: str
    dimension: Literal["month", "platform"]
    key: str
    label: str
    requested_start: date
    requested_end: date
    covered_start: date | None = None
    covered_end: date | None = None
    data_updated_at: datetime | None = None
    partial_coverage: bool
    sales: Decimal
    writeoff_count: int
    positive_count: int
    writeoff_rate: Decimal
    gross_profit: Decimal


class StrictToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyToolInput(StrictToolInput):
    pass


class ScenicQueryInput(StrictToolInput):
    scenic_ids: list[str] = Field(min_length=1, max_length=6)
    start_date: date
    end_date: date


class ScenicTrendInput(ScenicQueryInput):
    dimension: Literal["month", "platform"] = "month"


class ScenicComparisonInput(ScenicQueryInput):
    scenic_ids: list[str] = Field(min_length=2, max_length=6)


class NavigationInput(StrictToolInput):
    scenic_id: str = Field(min_length=1, max_length=128)


class AdminDeleteRequest(StrictAiModel):
    reason: str = Field(min_length=2, max_length=200)

    @field_validator("reason")
    @classmethod
    def reason_must_contain_visible_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("删除原因至少需要 2 个字符")
        return value


class AiDeletionAuditOut(StrictAiModel):
    id: int
    conversation_id: int
    owner_id: int
    actor_id: int | None
    mode: Literal["owner", "admin", "retention"]
    reason: str
    deleted_message_count: int
    deleted_at: datetime
