"""Async DeepSeek client using its OpenAI-compatible API."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import AsyncIterator, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal[
        "platform_overview",
        "portal_applications",
        "scenic_summary",
        "scenic_trend",
        "compare_scenics",
        "scenic_navigation",
        "free_form",
    ]
    scenic_ids: list[str] = Field(default_factory=list, max_length=6)
    date_text: str | None = Field(default=None, max_length=80)
    dimension: Literal["month", "platform"] | None = None


@dataclass(frozen=True)
class ModelAnswerChunk:
    text: str = ""
    finish_reason: str | None = None


def deepseek_client_options() -> dict:
    return {
        "api_key": settings.DEEPSEEK_API_KEY,
        "base_url": settings.DEEPSEEK_BASE_URL,
        "timeout": settings.AI_TIMEOUT_SECONDS,
    }


class DeepSeekChatClient:
    def __init__(self):
        self.client = AsyncOpenAI(**deepseek_client_options()) if settings.AI_ENABLED else None

    def _require_client(self) -> AsyncOpenAI:
        if self.client is None:
            raise RuntimeError("DeepSeek is not configured")
        return self.client

    async def classify(self, text: str, allowed_scenics: list[dict]) -> IntentDecision:
        response = await self._require_client().chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你只负责把问题分类为给定意图。仅返回 JSON，不回答问题，不生成 URL。"
                        "scenic_ids 只能使用给定 canonical id，无法确定时使用 free_form。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "question": text,
                        "allowed_scenics": allowed_scenics,
                        "intents": [
                            "platform_overview", "portal_applications", "scenic_summary",
                            "scenic_trend", "compare_scenics", "scenic_navigation", "free_form",
                        ],
                    }, ensure_ascii=False),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
            stream=False,
        )
        content = response.choices[0].message.content or "{}"
        return IntentDecision.model_validate_json(content)

    async def stream_answer(
        self, system_prompt: str, context: str
    ) -> AsyncIterator[ModelAnswerChunk]:
        stream = await self._require_client().chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ],
            stream=True,
            temperature=0.2,
        )
        async for chunk in stream:
            for choice in chunk.choices:
                text = choice.delta.content or ""
                finish_reason = choice.finish_reason
                if text or finish_reason is not None:
                    yield ModelAnswerChunk(text=text, finish_reason=finish_reason)
