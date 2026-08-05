# AI Assistant Conversations, Tools, Streaming, and Auditing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the portal's AI mount region with a secure, permission-aware, multi-conversation AI workspace that answers platform questions, queries authorized scenic aggregates, streams responses, returns user-clicked navigation actions, and supports retention plus administrator auditing.

**Architecture:** Persist conversations, messages, tool traces, and deletion receipts in MySQL; route every data question through deterministic intent/date parsing and a strict whitelist of aggregate-only tools. DeepSeek receives only the minimum validated aggregate result and streams natural-language output, while local templates preserve platform, scenic, comparison, and navigation functions during model outages. Redis-compatible runtime leases coordinate rate limits, duplicate suppression, concurrent generation, and stop requests across both production Uvicorn workers.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2.0, Pydantic 2, MySQL 8, Redis 5, OpenAI Python 1.59 `AsyncOpenAI`, DeepSeek OpenAI-compatible API, SSE over authenticated `fetch`, Vue 3.5, Pinia 2.3, marked 18, DOMPurify 3, Vitest 3, Playwright 1.55, Nginx, systemd

## Dependency

- Complete and verify `docs/superpowers/plans/2026-08-05-unified-portal-permissions-route-migration.md` first.
- This plan consumes `CompanyCode`, `ResourceCode`, `has_resource`, `applications_for_user`, `PortalHome`, `GlobalHeader`, `usePortalStore`, and the `/supplymanagement/*` named routes created there.

## Global Constraints

- The product name remains exactly `山东出版投资有限公司工作平台`.
- The AI workspace is the upper half of `/`; the three business-system cards remain a separate lower section and are never embedded inside the conversation panel.
- All authenticated users may ask platform-introduction questions.
- Scenic tools require backend authorization for `supplymanagement` and `supply.scenic.analytics` before any business query executes.
- AI is read-only: it cannot edit configuration, import or delete ledgers, start approvals, or execute any other business write.
- The model never receives or returns raw ledger rows, attachment content, account credentials, tokens, database structure, SQL, or internal calculation formulas.
- Navigation actions contain only a whitelisted action type and validated `scenic_id`; the backend and model never provide arbitrary URLs.
- Navigation happens only after a user click and maps to `/supplymanagement/cultural-tourism/:scenicId` in frontend code.
- Supported relative dates use `Asia/Shanghai` and include this month, last month, this year, last year, recent N months, a named month, quarter, year, and explicit start/end dates.
- Every data answer shows the actual requested range, actual covered range, and data update time; partial coverage is stated explicitly.
- DeepSeek output streams and users can stop generation.
- Only one generation may run in a conversation, at most two may run per user, and the configurable default rate limit is 20 message submissions per minute per user.
- Conversation retention is configurable and defaults to 180 days; a changed setting is applied to existing conversations at the next cleanup evaluation.
- Users may rename and manually delete their own conversations; information maintenance may inspect and delete any conversation with a required reason.
- The information maintainer is the existing sole `info_maintainer` superuser identity; no second administrator role is created.
- DeepSeek timeout, rate limiting, or outage preserves platform overview, scenic summary/trend/comparison, and navigation through local rules; free-form questions report temporary unavailability.
- Markdown rendering strips scripts, embedded media, external resources, arbitrary links, event handlers, and unsafe protocols.
- Production release is performed only after both implementation plans, migrations, security tests, stream tests, browser checks, and production build pass.

---

## File Structure

### Backend

- Create `backend/app/models/ai_assistant.py`: conversation, message, tool-call, and deletion-audit models.
- Create `backend/app/schemas/ai_assistant.py`: strict CRUD, streaming, tool, action, analytics, and admin contracts.
- Create `backend/app/services/ai_runtime.py`: cross-process rate, lease, deduplication, and cancellation state.
- Create `backend/app/services/ai_dates.py`: `Asia/Shanghai` date-range parser.
- Create `backend/app/services/scenic_analytics.py`: shared aggregate-only scenic analytics.
- Create `backend/app/services/ai_tools.py`: static tool registry and permission-checked execution.
- Create `backend/app/services/deepseek_chat.py`: asynchronous DeepSeek classification and streaming client.
- Create `backend/app/services/ai_orchestrator.py`: intent resolution, tools, model output, and deterministic fallback.
- Create `backend/app/services/ai_conversations.py`: ownership, CRUD, title generation, deletion, and stream persistence.
- Create `backend/app/api/v1/endpoints/ai_assistant.py`: user, streaming, stop, suggestion, and admin endpoints.
- Create `backend/app/jobs/cleanup_ai_conversations.py`: retention cleanup command.
- Create `backend/migrations/20260805_ai_assistant.sql`: idempotent AI tables and indexes.
- Create `backend/tests/test_ai_models.py`: persistence and deletion constraints.
- Create `backend/tests/test_ai_dates.py`: explicit and relative date boundaries.
- Create `backend/tests/test_scenic_analytics.py`: aggregate semantics and coverage metadata.
- Create `backend/tests/test_ai_tools.py`: whitelist, strict arguments, permissions, and navigation.
- Create `backend/tests/test_ai_orchestrator.py`: DeepSeek, fallback, and prompt-minimization behavior.
- Create `backend/tests/test_ai_conversations.py`: ownership, CRUD, retention, and audit deletion.
- Create `backend/tests/test_ai_streaming.py`: SSE order, idempotency, cancellation, disconnects, and limits.
- Modify `backend/app/core/config.py`: AI retention, limit, query-span, and shared-store settings.
- Modify `backend/app/core/store.py`: atomic lease and compare-delete operations needed by AI runtime.
- Modify `backend/app/models/__init__.py`: register AI models.
- Modify `backend/app/db/init_db.py`: register AI models only; do not seed conversation content.
- Modify `backend/app/api/v1/router.py`: register `/ai-assistant`.
- Modify `backend/app/api/v1/endpoints/scenic.py`: delegate current metrics to shared analytics.
- Modify `backend/app/services/financial.py`: share the same aggregation primitives.
- Modify `backend/app/api/v1/endpoints/health.py`: expose non-secret AI/shared-store readiness.

### Frontend

- Create `frontend/src/api/aiAssistant.js`: conversation CRUD, suggestions, SSE submission, stop, and admin clients.
- Create `frontend/src/utils/sse.js`: incremental authenticated SSE parser.
- Create `frontend/src/utils/safeMarkdown.js`: marked plus DOMPurify rendering policy.
- Create `frontend/src/store/aiAssistant.js`: sessions, messages, streaming state, restoration, and actions.
- Create `frontend/src/components/ai/AiWorkspace.vue`: responsive workspace composition.
- Create `frontend/src/components/ai/ConversationSidebar.vue`: create, switch, rename, and delete sessions.
- Create `frontend/src/components/ai/MessageList.vue`: messages, metadata, loading, and scroll restoration.
- Create `frontend/src/components/ai/MessageBubble.vue`: safe Markdown and structured actions.
- Create `frontend/src/components/ai/SuggestionList.vue`: permission-filtered starter prompts.
- Create `frontend/src/components/ai/MessageComposer.vue`: send/stop state machine.
- Create `frontend/src/views/system/ai-conversations.vue`: information-maintainer audit and delete view.
- Create `frontend/src/store/aiAssistant.test.js`: multi-session and stream state tests.
- Create `frontend/src/utils/sse.test.js`: chunk-boundary parser tests.
- Create `frontend/src/utils/safeMarkdown.test.js`: XSS and link-policy tests.
- Create `frontend/src/components/ai/AiWorkspace.test.js`: layout and interaction tests.
- Create `frontend/playwright.config.js`: desktop/mobile browser test runner.
- Create `frontend/e2e/portal-ai.spec.js`: portal, streaming, stop, action, and viewport tests.
- Modify `frontend/package.json` and `frontend/package-lock.json`: DOMPurify and Playwright dependencies/scripts.
- Modify `frontend/src/views/portal/index.vue`: replace the skeleton with `AiWorkspace`.
- Modify `frontend/src/router/index.js`: add the superuser AI audit route.
- Modify `frontend/src/layout/index.vue`: show the AI audit menu for the information maintainer.
- Modify `frontend/src/styles/_tokens.scss`: add balanced AI status/action colors.

### Operations

- Create `deploy/sd-scm-ai-cleanup.service`: one-shot retention command.
- Create `deploy/sd-scm-ai-cleanup.timer`: daily cleanup schedule.
- Modify `deploy/nginx.conf`: unbuffered long-lived SSE location.
- Modify `deploy/sd-scm-backend.service`: require configured Redis for multi-worker AI runtime.

---

### Task 1: Persist Conversations, Messages, Tool Traces, and Deletion Receipts

**Files:**
- Create: `backend/app/models/ai_assistant.py`
- Create: `backend/app/schemas/ai_assistant.py`
- Create: `backend/migrations/20260805_ai_assistant.sql`
- Create: `backend/tests/test_ai_models.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/init_db.py`

**Interfaces:**
- Produces: `AiConversation`, `AiMessage`, `AiToolCall`, and `AiDeletionAudit`.
- Produces: enum values `active`, `user`, `assistant`, `generating`, `completed`, `stopped`, `failed`, `owner`, `admin`, and `retention` as string columns.
- Guarantees: conversation deletion cascades to messages/tool calls, while `ai_deletion_audit` has no content-bearing foreign key and remains.

- [ ] **Step 1: Write failing model contract tests**

```python
# backend/tests/test_ai_models.py
import unittest

from app.models.ai_assistant import AiConversation, AiDeletionAudit, AiMessage


class AiModelContractTest(unittest.TestCase):
    def test_message_idempotency_is_scoped_to_conversation(self):
        unique_sets = {
            tuple(column.name for column in constraint.columns)
            for constraint in AiMessage.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("conversation_id", "client_message_id"), unique_sets)

    def test_deletion_receipt_does_not_reference_conversation_content(self):
        foreign_keys = {foreign_key.target_fullname for foreign_key in AiDeletionAudit.__table__.foreign_keys}
        self.assertNotIn("ai_conversation.id", foreign_keys)
        self.assertNotIn("content", AiDeletionAudit.__table__.columns)

    def test_conversation_has_retention_and_activity_fields(self):
        columns = set(AiConversation.__table__.columns.keys())
        self.assertTrue({"owner_id", "last_active_at", "expires_at"}.issubset(columns))
```

- [ ] **Step 2: Run the model tests and verify failure**

Run: `cd backend; python -m unittest tests.test_ai_models -v`

Expected: FAIL because `app.models.ai_assistant` does not exist.

- [ ] **Step 3: Add concrete models, strict schemas, and the SQL migration**

```python
# core columns in backend/app/models/ai_assistant.py
class AiConversation(Base):
    __tablename__ = "ai_conversation"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("sys_user.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="新会话")
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class AiMessage(Base):
    __tablename__ = "ai_message"
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_message_id", name="uq_ai_message_client"),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversation.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actions_json: Mapped[list] = mapped_column(JSON, default=list)
    data_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_covered_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_covered_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    engine: Mapped[str | None] = mapped_column(String(24), nullable=True)
    first_token_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

`AiToolCall` stores `tool_name`, sanitized `arguments_json`, `permission_decision`, `status`, `duration_ms`, and aggregate-only `result_summary_json`. `AiDeletionAudit` stores the numeric former conversation ID, owner ID, actor ID, mode, reason, deleted message count, and deletion time without message text or tool output. The message timing/engine fields plus structured request-completion logs provide request volume, success, first-token latency, total latency, model failures, active/stop status, and request-ID correlation without logging prompt or answer text.

Use MySQL `JSON`, foreign-key cascades, the same unique constraint, and indexes on owner/activity/status/request IDs. Import all four models before `Base.metadata.create_all`; seed no AI rows.

- [ ] **Step 4: Run model and full backend tests**

Run: `cd backend; python -m unittest tests.test_ai_models -v`

Expected: PASS.

Run: `cd backend; python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the AI persistence model**

```bash
git add backend/app/models/ai_assistant.py backend/app/schemas/ai_assistant.py backend/app/models/__init__.py backend/app/db/init_db.py backend/migrations/20260805_ai_assistant.sql backend/tests/test_ai_models.py
git commit -m "feat: persist AI assistant conversations"
```

### Task 2: Add Cross-Process Generation Leases, Limits, and Cancellation

**Files:**
- Create: `backend/app/services/ai_runtime.py`
- Create: `backend/tests/test_ai_streaming.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/store.py`
- Modify: `backend/app/api/v1/endpoints/health.py`

**Interfaces:**
- Produces: `acquire_generation(user_id, conversation_id, request_id) -> GenerationLease`.
- Produces: `release_generation(lease)`, `request_stop(message_id)`, and `is_stop_requested(message_id) -> bool`.
- Produces: `check_submission_rate(user_id) -> None` raising HTTP 429 after 20 submissions in 60 seconds.
- Adds atomic store methods `set_if_absent`, `compare_delete`, `set_members`, and `remove_member` with TTL.

- [ ] **Step 1: Write failing runtime coordination tests**

```python
# backend/tests/test_ai_streaming.py
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.services import ai_runtime


class AiRuntimeTest(unittest.TestCase):
    def setUp(self):
        ai_runtime.reset_for_tests()

    def test_only_one_generation_can_run_in_a_conversation(self):
        first = ai_runtime.acquire_generation(3, 10, "request-a")
        with self.assertRaises(HTTPException) as raised:
            ai_runtime.acquire_generation(3, 10, "request-b")
        self.assertEqual(raised.exception.status_code, 409)
        ai_runtime.release_generation(first)

    def test_stop_flag_is_visible_through_runtime_store(self):
        ai_runtime.request_stop(42)
        self.assertTrue(ai_runtime.is_stop_requested(42))
```

- [ ] **Step 2: Run the runtime tests and verify failure**

Run: `cd backend; python -m unittest tests.test_ai_streaming.AiRuntimeTest -v`

Expected: FAIL because `ai_runtime` does not exist.

- [ ] **Step 3: Implement atomic leases and exact settings**

```python
# backend/app/core/config.py
AI_CONVERSATION_RETENTION_DAYS: int = 180
AI_MAX_PROMPT_CHARS: int = 2000
AI_MAX_QUERY_MONTHS: int = 36
AI_REQUESTS_PER_MINUTE: int = 20
AI_MAX_CONCURRENT_PER_USER: int = 2
AI_GENERATION_LEASE_SECONDS: int = 300
AI_SHARED_STORE_REQUIRED: bool = False
```

Use keys `ai:conversation:{conversation_id}:lease`, `ai:user:{user_id}:active`, `ai:user:{user_id}:rate`, and `ai:message:{message_id}:stop`. Redis operations must be atomic; memory implementations use the existing lock. Lease release must compare the stored request ID before deletion so an expired/reacquired lease cannot be removed by an older request.

When `AI_SHARED_STORE_REQUIRED=true` and `backend_name() != 'redis'`, fail application startup with a configuration error. The health response exposes only `ai_shared_store: "ready" | "not_configured"`, never `REDIS_URL`.

- [ ] **Step 4: Run runtime and health tests**

Run: `cd backend; python -m unittest tests.test_ai_streaming.AiRuntimeTest -v`

Expected: PASS.

Run: `cd backend; python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit runtime coordination**

```bash
git add backend/app/core/config.py backend/app/core/store.py backend/app/services/ai_runtime.py backend/app/api/v1/endpoints/health.py backend/tests/test_ai_streaming.py
git commit -m "feat: coordinate AI generation across workers"
```

### Task 3: Centralize Scenic Aggregates and Resolve Shanghai Date Ranges

**Files:**
- Create: `backend/app/services/ai_dates.py`
- Create: `backend/app/services/scenic_analytics.py`
- Create: `backend/tests/test_ai_dates.py`
- Create: `backend/tests/test_scenic_analytics.py`
- Modify: `backend/app/api/v1/endpoints/scenic.py`
- Modify: `backend/app/services/financial.py`
- Modify: `backend/app/schemas/ai_assistant.py`

**Interfaces:**
- Produces: `DateRange(start: date, end: date, label: str)` and `resolve_date_range(text, now) -> DateRange | None`.
- Produces: `ScenicAnalyticsService.summary(scenic_ids, date_range) -> list[ScenicSummary]`.
- Produces: `ScenicAnalyticsService.trend(scenic_ids, date_range, dimension) -> list[ScenicTrendPoint]`.
- Produces: requested/covered date metadata and `data_updated_at` on every result.

- [ ] **Step 1: Write failing date and aggregation tests**

```python
# backend/tests/test_ai_dates.py
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.ai_dates import resolve_date_range


class AiDateRangeTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 5, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    def test_last_month_uses_calendar_boundaries(self):
        value = resolve_date_range("上个月", self.now)
        self.assertEqual(value.start.isoformat(), "2026-07-01")
        self.assertEqual(value.end.isoformat(), "2026-07-31")

    def test_recent_three_months_includes_current_partial_month(self):
        value = resolve_date_range("最近三个月", self.now)
        self.assertEqual(value.start.isoformat(), "2026-06-01")
        self.assertEqual(value.end.isoformat(), "2026-08-05")
```

```python
# backend/tests/test_scenic_analytics.py
import unittest
from datetime import date, datetime
from decimal import Decimal

from app.models.ticket_ledger import TicketLedger
from app.services.scenic_analytics import aggregate_rows


class ScenicAnalyticsTest(unittest.TestCase):
    def test_summary_returns_aggregates_and_partial_coverage_only(self):
        rows = [TicketLedger(
            scenic_id="zunyi-zoo", period_start=date(2026, 7, 1), period_end=date(2026, 7, 20),
            jinying_amount=Decimal("870"), service_fee=Decimal("30"), payment_amount=Decimal("1000"),
            co_investment_amount=Decimal("100"), order_count=10, positive_count=8,
            updated_at=datetime(2026, 7, 21, 9, 0), platform="抖音"
        )]
        result = aggregate_rows(rows, [], date(2026, 7, 1), date(2026, 7, 31))[0]
        self.assertEqual(result.sales, Decimal("870"))
        self.assertEqual(result.writeoff_rate, Decimal("80.00"))
        self.assertEqual(result.covered_end.isoformat(), "2026-07-20")
        self.assertTrue(result.partial_coverage)
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `cd backend; python -m unittest tests.test_ai_dates tests.test_scenic_analytics -v`

Expected: FAIL because the date and shared analytics modules do not exist.

- [ ] **Step 3: Implement parsing, aggregation, and existing-page delegation**

`resolve_date_range` must support `本月`, `上个月`, `今年`, `去年`, `最近N个月`, `YYYY年M月`, `YYYY年第N季度`, `YYYY年`, and `YYYY-MM-DD至YYYY-MM-DD`. Reject inverted ranges and ranges longer than `AI_MAX_QUERY_MONTHS`.

```python
# backend/app/services/scenic_analytics.py
@dataclass(frozen=True)
class ScenicSummary:
    scenic_id: str
    scenic_name: str
    requested_start: date
    requested_end: date
    covered_start: date | None
    covered_end: date | None
    data_updated_at: datetime | None
    partial_coverage: bool
    sales: Decimal
    writeoff_count: int
    positive_count: int
    writeoff_rate: Decimal
    existing_scale: Decimal
    realized_scale: Decimal
    gross_profit: Decimal
    capital_occupation_days: float | None
    ticket_total: Decimal
    hotel_total: Decimal
```

Filter by `period_end` falling within the requested range, falling back to `period_start` only when `period_end` is null. Exclude undated rows from date-bounded answers and report them nowhere. Group trends by month or platform from aggregate rows only.

Refactor scenic `get_metrics` to call the shared summary and preserve its existing response keys. Refactor `financial.build_ledger_metrics` to call shared internal aggregation primitives so page and AI calculations cannot diverge.

- [ ] **Step 4: Run analytics and existing financial tests**

Run: `cd backend; python -m unittest tests.test_ai_dates tests.test_scenic_analytics tests.test_financial_ledger_metrics -v`

Expected: PASS, including existing dashboard totals.

- [ ] **Step 5: Commit shared analytics**

```bash
git add backend/app/services/ai_dates.py backend/app/services/scenic_analytics.py backend/app/schemas/ai_assistant.py backend/app/api/v1/endpoints/scenic.py backend/app/services/financial.py backend/tests/test_ai_dates.py backend/tests/test_scenic_analytics.py
git commit -m "feat: centralize scenic AI analytics"
```

### Task 4: Build Strict Permission-Checked Whitelisted Tools

**Files:**
- Create: `backend/app/services/ai_tools.py`
- Create: `backend/tests/test_ai_tools.py`
- Modify: `backend/app/schemas/ai_assistant.py`

**Interfaces:**
- Produces exactly six registered tools: `get_platform_overview`, `get_portal_applications`, `get_scenic_summary`, `get_scenic_trend`, `compare_scenics`, `create_scenic_navigation_action`.
- Produces: `ToolContext(db: Session, user: User, request_id: str)`.
- Produces: `execute_tool(name: str, arguments: dict, context: ToolContext) -> ToolResult`.
- Produces action shape `{type: "navigate_to_scenic", scenic_id: str, label: str}` without a URL field.

- [ ] **Step 1: Write failing whitelist and permission tests**

```python
# backend/tests/test_ai_tools.py
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app.services.ai_tools import TOOL_REGISTRY, ToolContext, execute_tool


class AiToolSecurityTest(unittest.TestCase):
    def test_registry_contains_only_approved_tools(self):
        self.assertEqual(set(TOOL_REGISTRY), {
            "get_platform_overview", "get_portal_applications", "get_scenic_summary",
            "get_scenic_trend", "compare_scenics", "create_scenic_navigation_action"
        })

    def test_navigation_rejects_arbitrary_url(self):
        context = ToolContext(db=Mock(), user=SimpleNamespace(id=2, is_superuser=False), request_id="r1")
        with self.assertRaises(ValidationError):
            execute_tool("create_scenic_navigation_action", {
                "scenic_id": "zunyi-zoo", "url": "https://example.com"
            }, context)

    @patch("app.services.ai_tools.has_resource", return_value=False)
    def test_scenic_query_stops_before_database_access(self, denied):
        db = Mock()
        context = ToolContext(db=db, user=SimpleNamespace(id=2, is_superuser=False), request_id="r2")
        with self.assertRaises(PermissionError):
            execute_tool("get_scenic_summary", {
                "scenic_ids": ["zunyi-zoo"], "start_date": "2026-07-01", "end_date": "2026-07-31"
            }, context)
        db.scalars.assert_not_called()
```

- [ ] **Step 2: Run tool tests and verify failure**

Run: `cd backend; python -m unittest tests.test_ai_tools -v`

Expected: FAIL because `ai_tools` does not exist.

- [ ] **Step 3: Implement strict Pydantic inputs and static registry**

```python
class StrictToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenicQueryInput(StrictToolInput):
    scenic_ids: list[str] = Field(min_length=1, max_length=6)
    start_date: date
    end_date: date


class NavigationInput(StrictToolInput):
    scenic_id: str = Field(min_length=1, max_length=64)
```

Resolve scenic IDs only through `ScenicConfig`; accept configured aliases but emit canonical IDs. Check `has_resource(..., CompanyCode.SUPPLY_MANAGEMENT, ResourceCode.SCENIC_ANALYTICS)` before loading ledger rows. Every tool-call audit stores only canonical IDs, dates, dimensions, permission decision, timing, counts, and total values; it never stores row-level inputs or formulas.

- [ ] **Step 4: Run tool and permission tests**

Run: `cd backend; python -m unittest tests.test_ai_tools tests.test_company_permissions -v`

Expected: PASS.

- [ ] **Step 5: Commit whitelisted tools**

```bash
git add backend/app/services/ai_tools.py backend/app/schemas/ai_assistant.py backend/tests/test_ai_tools.py
git commit -m "feat: add permission checked AI tools"
```

### Task 5: Add Async DeepSeek Streaming and Deterministic Fallback Orchestration

**Files:**
- Create: `backend/app/services/deepseek_chat.py`
- Create: `backend/app/services/ai_orchestrator.py`
- Create: `backend/tests/test_ai_orchestrator.py`
- Modify: `backend/app/services/ai_agent.py`

**Interfaces:**
- Produces: `DeepSeekChatClient.classify(text, allowed_scenics) -> IntentDecision`.
- Produces: `DeepSeekChatClient.stream_answer(system_prompt, context) -> AsyncIterator[str]`.
- Produces: `AiOrchestrator.stream(question, context) -> AsyncIterator[OrchestratorEvent]`.
- `OrchestratorEvent.kind` is one of `tool.status`, `text.delta`, `action`, or `error`.

- [ ] **Step 1: Write failing outage and data-minimization tests**

```python
# backend/tests/test_ai_orchestrator.py
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services.ai_orchestrator import AiOrchestrator


async def _async_chunks(text):
    for chunk in (text[:2], text[2:]):
        if chunk:
            yield chunk


class OfflineClient:
    async def classify(self, *args, **kwargs):
        raise RuntimeError("offline")

    async def stream_answer(self, *args, **kwargs):
        raise RuntimeError("offline")
        yield ""


class RecordingClient:
    def __init__(self):
        self.context = ""

    def stream_answer(self, system_prompt, context):
        self.context = context
        return _async_chunks("遵义动物园数据")


class AiOrchestratorTest(unittest.IsolatedAsyncioTestCase):
    async def test_platform_overview_works_without_deepseek(self):
        orchestrator = AiOrchestrator(client=OfflineClient())
        events = [event async for event in orchestrator.stream("这个平台是做什么的？", Mock())]
        text = "".join(event.payload.get("text", "") for event in events)
        self.assertIn("山东出版投资有限公司工作平台", text)
        self.assertIn("供应链管理", text)

    async def test_free_form_reports_unavailable_when_model_is_offline(self):
        orchestrator = AiOrchestrator(client=OfflineClient())
        events = [event async for event in orchestrator.stream("写一首诗", Mock())]
        text = "".join(event.payload.get("text", "") for event in events)
        self.assertIn("AI 服务暂时不可用", text)

    @patch("app.services.ai_orchestrator.execute_tool")
    async def test_model_context_contains_aggregate_result_not_ledger_rows(self, execute_tool):
        execute_tool.return_value.data = {"sales": "870.00", "writeoff_count": 10}
        client = RecordingClient()
        orchestrator = AiOrchestrator(client=client)
        _ = [event async for event in orchestrator.stream("遵义动物园上月数据", Mock())]
        prompt = client.context
        self.assertNotIn("daily_json", prompt)
        self.assertNotIn("source_file", prompt)
```

- [ ] **Step 2: Run orchestrator tests and verify failure**

Run: `cd backend; python -m unittest tests.test_ai_orchestrator -v`

Expected: FAIL because the async client and orchestrator do not exist.

- [ ] **Step 3: Implement local-first intent resolution and async streaming**

```python
# backend/app/services/deepseek_chat.py
class DeepSeekChatClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )

    async def stream_answer(self, system_prompt: str, context: str):
        stream = await self.client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": context}],
            stream=True,
            temperature=0.2,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta
```

The orchestrator first resolves controlled overview, company status, scenic alias, date, trend/comparison, and navigation expressions locally. It uses model classification only when the local result is ambiguous, validates the returned intent against a Pydantic enum, and then invokes the same permission-checked tool registry. The answer prompt explicitly forbids formulas and receives only serialized `ToolResult.data`.

On DeepSeek timeout/rate-limit/error, render deterministic Chinese templates for controlled intents and preserve validated actions. If a multi-scenic/tool request has partial data, keep successful aggregates and explicitly list missing scenic/range results instead of describing the response as complete. For free-form intent, emit exactly `AI 服务暂时不可用，请稍后重试。` Do not add a second cloud model.

Leave existing synchronous `ai_agent.diagnose` behavior intact; share only client configuration helpers so current page AI does not regress.

- [ ] **Step 4: Run orchestrator and current AI regression tests**

Run: `cd backend; python -m unittest tests.test_ai_orchestrator tests.test_ai_tools tests.test_financial_ledger_metrics -v`

Expected: PASS.

- [ ] **Step 5: Commit orchestration and fallback**

```bash
git add backend/app/services/deepseek_chat.py backend/app/services/ai_orchestrator.py backend/app/services/ai_agent.py backend/tests/test_ai_orchestrator.py
git commit -m "feat: orchestrate streaming AI answers"
```

### Task 6: Implement Conversation CRUD, Suggestions, Ownership, and Deletion

**Files:**
- Create: `backend/app/services/ai_conversations.py`
- Create: `backend/app/api/v1/endpoints/ai_assistant.py`
- Create: `backend/tests/test_ai_conversations.py`
- Modify: `backend/app/api/v1/router.py`

**Interfaces:**
- Produces all user CRUD endpoints under `/api/v1/ai-assistant` from the specification.
- Produces: `GET /suggestions` filtered by `ResourceCode.SCENIC_ANALYTICS`.
- Guarantees: only the owner or information-maintainer may load a conversation; user deletion can delete only the owner’s conversation.

- [ ] **Step 1: Write failing ownership and suggestion tests**

```python
# backend/tests/test_ai_conversations.py
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.services.ai_conversations import get_owned_conversation, suggestions_for_user


class AiConversationOwnershipTest(unittest.TestCase):
    def test_other_user_cannot_read_conversation(self):
        db = Mock()
        db.get.return_value = SimpleNamespace(id=9, owner_id=100)
        with self.assertRaises(HTTPException) as raised:
            get_owned_conversation(db, conversation_id=9, user_id=101)
        self.assertEqual(raised.exception.status_code, 404)

    @patch("app.services.ai_conversations.has_resource", return_value=False)
    def test_user_without_scenic_resource_gets_platform_suggestions_only(self, denied):
        questions = suggestions_for_user(Mock(), SimpleNamespace(is_superuser=False))
        self.assertEqual(questions, [
            "这个平台是做什么的？",
            "介绍一下三个业务系统的建设情况。",
        ])
```

- [ ] **Step 2: Run conversation tests and verify failure**

Run: `cd backend; python -m unittest tests.test_ai_conversations -v`

Expected: FAIL because the conversation service is missing.

- [ ] **Step 3: Implement CRUD, title generation, and hard deletion receipts**

Implement:

```text
GET    /ai-assistant/conversations
POST   /ai-assistant/conversations
GET    /ai-assistant/conversations/{id}
PATCH  /ai-assistant/conversations/{id}
DELETE /ai-assistant/conversations/{id}
GET    /ai-assistant/suggestions
```

List newest `last_active_at` first and paginate with `page>=1`, `size<=50`. New conversations use `新会话`; after the first completed user/assistant pair, replace it with the first 24 visible Chinese characters of the question, stripping markup and line breaks. Rename accepts 1-120 characters.

Owner deletion creates one `AiDeletionAudit(mode="owner", reason="用户主动删除")`, records the message count, and then hard-deletes the conversation in one transaction. Return 404 rather than 403 for another user's ID to avoid enumeration.

- [ ] **Step 4: Run CRUD, permission, and router tests**

Run: `cd backend; python -m unittest tests.test_ai_conversations tests.test_company_permissions -v`

Expected: PASS.

Run: `cd backend; python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit conversation APIs**

```bash
git add backend/app/services/ai_conversations.py backend/app/api/v1/endpoints/ai_assistant.py backend/app/api/v1/router.py backend/tests/test_ai_conversations.py
git commit -m "feat: add AI conversation APIs"
```

### Task 7: Stream Message Events, Stop Generation, and Prevent Duplicates

**Files:**
- Modify: `backend/app/api/v1/endpoints/ai_assistant.py`
- Modify: `backend/app/services/ai_conversations.py`
- Modify: `backend/app/services/ai_runtime.py`
- Modify: `backend/tests/test_ai_streaming.py`

**Interfaces:**
- Produces: `POST /conversations/{id}/messages` with `text/event-stream`.
- Produces: `POST /messages/{id}/stop`.
- Accepts: `{content: str, client_message_id: UUID}`.
- Emits ordered SSE event names `message.created`, `tool.status`, `text.delta`, `action`, `message.completed`, `message.stopped`, and `error`.

- [ ] **Step 1: Add failing SSE order, deduplication, and stop tests**

```python
# append to backend/tests/test_ai_streaming.py
from app.services.ai_conversations import encode_sse


class AiSseContractTest(unittest.TestCase):
    def test_sse_frame_has_event_and_single_json_data_line(self):
        frame = encode_sse("text.delta", {"request_id": "r1", "text": "遵义"})
        self.assertEqual(
            frame,
            'event: text.delta\ndata: {"request_id":"r1","text":"遵义"}\n\n',
        )

    def test_terminal_events_are_explicit(self):
        self.assertIn("message.completed", {"message.completed", "message.stopped", "error"})
```

Add an endpoint integration fixture with an existing `(conversation_id, client_message_id)` and assert the second submission returns 409 without creating another user message. Add a generator test that sets the stop flag after one delta and asserts `message.stopped` is terminal and the persisted assistant status is `stopped`.

- [ ] **Step 2: Run streaming tests and verify failure**

Run: `cd backend; python -m unittest tests.test_ai_streaming -v`

Expected: FAIL because SSE encoding and message streaming are absent.

- [ ] **Step 3: Implement the streaming lifecycle**

The endpoint sequence is fixed:

1. Validate owner, prompt length, rate limit, and stable client message ID.
2. Acquire conversation/user leases.
3. Persist the user message and empty `generating` assistant message with one UUID request ID.
4. Return `StreamingResponse(generator, media_type="text/event-stream")` with `Cache-Control: no-cache`, `X-Accel-Buffering: no`, and `X-Request-ID: <request_id>`.
5. Emit `message.created`, then tool/delta/action events.
6. Check both `request.is_disconnected()` and `is_stop_requested(assistant_message.id)` between chunks.
7. Persist final content, metadata, action array, status, tool audit, title, activity, and recalculated expiry.
8. Emit exactly one terminal event, persist `engine`, first-token latency, total latency, and error code, write one content-free structured completion log, and release leases in `finally`.

Use compact JSON with `ensure_ascii=False`:

```python
def encode_sse(event: str, payload: dict) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n"
```

The stop endpoint verifies message ownership before setting the cross-process flag. If the message is already terminal, return its current status without mutation.

- [ ] **Step 4: Run streaming, orchestrator, and full backend tests**

Run: `cd backend; python -m unittest tests.test_ai_streaming tests.test_ai_orchestrator -v`

Expected: PASS.

Run: `cd backend; python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the streaming API**

```bash
git add backend/app/api/v1/endpoints/ai_assistant.py backend/app/services/ai_conversations.py backend/app/services/ai_runtime.py backend/tests/test_ai_streaming.py
git commit -m "feat: stream and stop AI messages"
```

### Task 8: Add Information-Maintainer Auditing and Retention Cleanup

**Files:**
- Create: `backend/app/jobs/cleanup_ai_conversations.py`
- Modify: `backend/app/api/v1/endpoints/ai_assistant.py`
- Modify: `backend/app/services/ai_conversations.py`
- Modify: `backend/tests/test_ai_conversations.py`

**Interfaces:**
- Produces the four `/ai-assistant/admin/*` endpoints from the specification.
- Produces: `cleanup_expired_conversations(now: datetime) -> CleanupResult`.
- Requires: admin deletion reason length 2-200 characters.
- Guarantees: cleanup recalculates the cutoff from the current retention setting each run.

- [ ] **Step 1: Add failing admin and retention tests**

```python
# append to backend/tests/test_ai_conversations.py
from datetime import datetime, timedelta

from app.services.ai_conversations import cleanup_expired_conversations


class AiRetentionTest(unittest.TestCase):
    @patch("app.services.ai_conversations.settings.AI_CONVERSATION_RETENTION_DAYS", 90)
    def test_changed_retention_applies_to_existing_conversations(self):
        now = datetime(2026, 8, 5, 1, 0)
        db = Mock()
        stale = SimpleNamespace(id=5, owner_id=2, last_active_at=now - timedelta(days=91), messages=[1, 2])
        db.scalars.return_value.all.return_value = [stale]
        result = cleanup_expired_conversations(db, now=now)
        self.assertEqual(result.deleted_conversations, 1)
        self.assertEqual(result.deleted_messages, 2)

    def test_admin_delete_requires_a_reason(self):
        from app.schemas.ai_assistant import AdminDeleteRequest
        with self.assertRaises(ValueError):
            AdminDeleteRequest(reason="")
```

- [ ] **Step 2: Run retention tests and verify failure**

Run: `cd backend; python -m unittest tests.test_ai_conversations.AiRetentionTest -v`

Expected: FAIL because cleanup and admin deletion schema are absent.

- [ ] **Step 3: Implement admin filters, deletion receipts, and cleanup command**

Admin list filters are `user_id`, `started_at`, `ended_at`, `status`, `keyword`, `page`, and `size`; keyword searches conversation title and message content but is available only through `require_superuser`. The detail endpoint returns the conversation, messages, and sanitized tool traces. No export endpoint is added.

Admin deletion creates `AiDeletionAudit(mode="admin", reason=<required reason>)`; retention creates `mode="retention"`, `reason="超过当前会话保留期"`. Both hard-delete content and structured actions/tool results. The cleanup query uses:

```python
cutoff = now - timedelta(days=settings.AI_CONVERSATION_RETENTION_DAYS)
select(AiConversation).where(AiConversation.last_active_at < cutoff).limit(500)
```

The module command opens `SessionLocal`, deletes batches until none remain, logs batch count, conversation count, message count, elapsed time, and errors without logging content, then exits nonzero on an unrecovered DB error.

- [ ] **Step 4: Run admin, retention, and deletion tests**

Run: `cd backend; python -m unittest tests.test_ai_conversations tests.test_ai_models -v`

Expected: PASS.

Run: `cd backend; python -m app.jobs.cleanup_ai_conversations --dry-run`

Expected: exit 0 and print counts without deleting rows.

- [ ] **Step 5: Commit auditing and cleanup**

```bash
git add backend/app/jobs/cleanup_ai_conversations.py backend/app/api/v1/endpoints/ai_assistant.py backend/app/services/ai_conversations.py backend/app/schemas/ai_assistant.py backend/tests/test_ai_conversations.py
git commit -m "feat: audit and retain AI conversations"
```

### Task 9: Build the Authenticated SSE Client and Multi-Conversation Store

**Files:**
- Create: `frontend/src/api/aiAssistant.js`
- Create: `frontend/src/utils/sse.js`
- Create: `frontend/src/utils/sse.test.js`
- Create: `frontend/src/store/aiAssistant.js`
- Create: `frontend/src/store/aiAssistant.test.js`

**Interfaces:**
- Produces: `streamMessage(conversationId, payload, {signal, onEvent}) -> Promise<void>`.
- Produces: Pinia actions `initialize`, `createConversation`, `openConversation`, `renameConversation`, `deleteConversation`, `sendMessage`, and `stopGeneration`.
- Persists: `ai:lastConversationId:<userId>` and `ai:scroll:<conversationId>` only; message content remains server-owned.

- [ ] **Step 1: Write failing chunk parser and store tests**

```javascript
// frontend/src/utils/sse.test.js
import { describe, expect, it } from 'vitest'
import { createSseParser } from './sse'

describe('SSE parser', () => {
  it('parses a UTF-8 event split across chunks', () => {
    const events = []
    const parser = createSseParser((event) => events.push(event))
    parser.push('event: text.delta\ndata: {"text":"遵')
    parser.push('义"}\n\n')
    expect(events).toEqual([{ event: 'text.delta', data: { text: '遵义' } }])
  })
})
```

```javascript
// frontend/src/store/aiAssistant.test.js
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAiAssistantStore } from './aiAssistant'
import * as api from '@/api/aiAssistant'

vi.mock('@/api/aiAssistant')

describe('AI assistant store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('blocks duplicate sends only in the active generating conversation', async () => {
    const store = useAiAssistantStore()
    store.conversations = [{ id: 1 }, { id: 2 }]
    store.generatingByConversation[1] = true
    expect(store.canSend(1)).toBe(false)
    expect(store.canSend(2)).toBe(true)
  })
})
```

- [ ] **Step 2: Run frontend state tests and verify failure**

Run: `cd frontend; npm test -- src/utils/sse.test.js src/store/aiAssistant.test.js`

Expected: FAIL because the parser and store do not exist.

- [ ] **Step 3: Implement streaming fetch and the session state machine**

```javascript
// frontend/src/api/aiAssistant.js
export async function streamMessage(conversationId, payload, { signal, onEvent }) {
  const response = await fetch(`/api/v1/ai-assistant/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${localStorage.getItem('token')}`,
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    body: JSON.stringify(payload),
    signal
  })
  if (!response.ok) throw await responseError(response)
  const parser = createSseParser(onEvent)
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    parser.push(decoder.decode(value, { stream: true }))
  }
  parser.push(decoder.decode())
  parser.finish()
}
```

Generate one `crypto.randomUUID()` per user submission and reuse it across network retry prompts. Store generation state by conversation ID, not globally. Switching sessions never aborts a stream; `stopGeneration` calls the backend stop endpoint and then aborts only after the stop response or a five-second timeout.

- [ ] **Step 4: Run parser/store tests**

Run: `cd frontend; npm test -- src/utils/sse.test.js src/store/aiAssistant.test.js`

Expected: PASS.

- [ ] **Step 5: Commit the frontend AI state layer**

```bash
git add frontend/src/api/aiAssistant.js frontend/src/utils/sse.js frontend/src/utils/sse.test.js frontend/src/store/aiAssistant.js frontend/src/store/aiAssistant.test.js
git commit -m "feat: manage streaming AI conversations"
```

### Task 10: Render Safe Markdown and Validated Navigation Actions

**Files:**
- Create: `frontend/src/utils/safeMarkdown.js`
- Create: `frontend/src/utils/safeMarkdown.test.js`
- Create: `frontend/src/components/ai/MessageBubble.vue`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Produces: `renderSafeMarkdown(markdown: string) -> string`.
- Produces: `validatedAction(action) -> {type, scenic_id, label} | null`.
- Maps valid actions to named route `CulturalTourismDetail` only after a click.

- [ ] **Step 1: Install DOMPurify and write failing security tests**

Run: `cd frontend; npm install dompurify@^3.2.6`

```javascript
// frontend/src/utils/safeMarkdown.test.js
import { describe, expect, it } from 'vitest'
import { renderSafeMarkdown, validatedAction } from './safeMarkdown'

describe('safe AI output', () => {
  it('removes scripts, event handlers, images, and external links', () => {
    const html = renderSafeMarkdown('[外链](https://evil.example)<img src=x onerror=alert(1)><script>alert(1)</script>')
    expect(html).not.toContain('script')
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('img')
    expect(html).not.toContain('href=')
  })

  it('rejects URL-bearing actions', () => {
    expect(validatedAction({ type: 'navigate_to_scenic', scenic_id: 'zunyi-zoo', label: '前往', url: 'https://evil.example' })).toBeNull()
  })
})
```

- [ ] **Step 2: Run security tests and verify failure**

Run: `cd frontend; npm test -- src/utils/safeMarkdown.test.js`

Expected: FAIL because the safe renderer does not exist.

- [ ] **Step 3: Implement the sanitizer and action whitelist**

```javascript
export function renderSafeMarkdown(source) {
  const raw = marked.parse(source || '', { gfm: true, breaks: true })
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
    ALLOWED_ATTR: []
  })
}

export function validatedAction(action) {
  if (!action || Object.keys(action).some((key) => !['type', 'scenic_id', 'label'].includes(key))) return null
  if (action.type !== 'navigate_to_scenic') return null
  if (!/^[a-z0-9-]{1,64}$/.test(action.scenic_id || '')) return null
  if (!action.label || action.label.length > 80) return null
  return { type: action.type, scenic_id: action.scenic_id, label: action.label }
}
```

`MessageBubble` renders sanitized HTML and an Element Plus location-icon button for each validated action. The button uses `router.push({ name: 'CulturalTourismDetail', params: { scenicId } })`; it never reads a route or URL from the action.

- [ ] **Step 4: Run security tests and build**

Run: `cd frontend; npm test -- src/utils/safeMarkdown.test.js`

Expected: PASS.

Run: `cd frontend; npm run build`

Expected: PASS.

- [ ] **Step 5: Commit safe message rendering**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/utils/safeMarkdown.js frontend/src/utils/safeMarkdown.test.js frontend/src/components/ai/MessageBubble.vue
git commit -m "feat: safely render AI responses"
```

### Task 11: Build the Portal AI Workspace and Restore Sessions

**Files:**
- Create: `frontend/src/components/ai/AiWorkspace.vue`
- Create: `frontend/src/components/ai/ConversationSidebar.vue`
- Create: `frontend/src/components/ai/MessageList.vue`
- Create: `frontend/src/components/ai/SuggestionList.vue`
- Create: `frontend/src/components/ai/MessageComposer.vue`
- Create: `frontend/src/components/ai/AiWorkspace.test.js`
- Modify: `frontend/src/views/portal/index.vue`
- Modify: `frontend/src/styles/_tokens.scss`

**Interfaces:**
- Consumes: `useAiAssistantStore` and `MessageBubble`.
- Emits no arbitrary navigation; child action buttons use the validated named-route mapping.
- Restores the latest opened conversation and per-conversation scroll position for the authenticated user.

- [ ] **Step 1: Write failing workspace interaction tests**

```javascript
// frontend/src/components/ai/AiWorkspace.test.js
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import AiWorkspace from './AiWorkspace.vue'
import { useAiAssistantStore } from '@/store/aiAssistant'

describe('AI workspace', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('keeps conversation and business regions independent', () => {
    const store = useAiAssistantStore()
    vi.spyOn(store, 'initialize').mockResolvedValue()
    const wrapper = mount(AiWorkspace, { global: { stubs: true } })
    expect(wrapper.attributes('data-workspace')).toBe('ai')
    expect(wrapper.find('[data-testid="conversation-sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="message-composer"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="application-entry"]').exists()).toBe(false)
  })

  it('shows stop instead of send while the active conversation generates', async () => {
    const store = useAiAssistantStore()
    vi.spyOn(store, 'initialize').mockResolvedValue()
    store.activeConversationId = 1
    store.generatingByConversation = { 1: true }
    const wrapper = mount(AiWorkspace, { global: { stubs: true } })
    expect(wrapper.find('[aria-label="停止生成"]').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run workspace tests and verify failure**

Run: `cd frontend; npm test -- src/components/ai/AiWorkspace.test.js`

Expected: FAIL because workspace components do not exist.

- [ ] **Step 3: Implement the complete responsive workspace**

Desktop uses a fixed-width conversation sidebar and a flexible message/composer column inside the upper portal band. Message scrolling is internal so the lower system region stays discoverable. Mobile moves the sidebar into an Element Plus drawer and stacks the message area/composer without horizontal overflow.

Required states:

- initial loading and API error with retry;
- empty new conversation with permission-filtered suggestions;
- multiple sessions with create, switch, inline rename, delete confirmation;
- user and assistant messages, tool progress, range/update metadata, stopped and failed states;
- composer validation, Enter-to-send, IME-safe handling, send, and stop;
- stable widths/heights so loading labels and stop/send controls do not shift surrounding layout.

Replace the portal skeleton with:

```vue
<section data-testid="assistant-region" class="assistant-region" aria-label="AI 智能助手">
  <AiWorkspace />
</section>
```

Keep the existing lower application region untouched.

- [ ] **Step 4: Run component/store tests and build**

Run: `cd frontend; npm test -- src/components/ai/AiWorkspace.test.js src/store/aiAssistant.test.js src/views/portal/index.test.js`

Expected: PASS.

Run: `cd frontend; npm run build`

Expected: PASS.

- [ ] **Step 5: Commit the AI workspace**

```bash
git add frontend/src/components/ai/AiWorkspace.vue frontend/src/components/ai/ConversationSidebar.vue frontend/src/components/ai/MessageList.vue frontend/src/components/ai/SuggestionList.vue frontend/src/components/ai/MessageComposer.vue frontend/src/components/ai/AiWorkspace.test.js frontend/src/views/portal/index.vue frontend/src/styles/_tokens.scss
git commit -m "feat: build portal AI workspace"
```

### Task 12: Add the Information-Maintainer Conversation Audit View

**Files:**
- Create: `frontend/src/views/system/ai-conversations.vue`
- Create: `frontend/src/views/system/ai-conversations.test.js`
- Modify: `frontend/src/api/aiAssistant.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layout/index.vue`

**Interfaces:**
- Produces route `/supplymanagement/ai-conversations` with `requiresSuperuser=true` and resource `supply.admin`.
- Produces admin API methods `listAdminConversations`, `getAdminConversation`, `deleteAdminConversation`, and `listDeletionAudits`.
- Requires a reason before enabling the admin delete confirmation action.

- [ ] **Step 1: Write failing audit-view behavior tests**

```javascript
// frontend/src/views/system/ai-conversations.test.js
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import View from './ai-conversations.vue'

describe('AI conversation audit view', () => {
  it('does not expose an export action', () => {
    const wrapper = mount(View, { global: { stubs: true } })
    expect(wrapper.text()).not.toContain('导出')
  })

  it('requires a deletion reason', async () => {
    const wrapper = mount(View, { global: { stubs: true } })
    expect(wrapper.find('[data-testid="confirm-admin-delete"]').attributes('disabled')).toBeDefined()
  })
})
```

- [ ] **Step 2: Run audit-view tests and verify failure**

Run: `cd frontend; npm test -- src/views/system/ai-conversations.test.js`

Expected: FAIL because the view does not exist.

- [ ] **Step 3: Implement filters, detail drawer, deletion dialog, and audit tab**

The view provides user, start/end date, status, and keyword filters; a paginated conversation table; a read-only detail drawer; a deletion dialog requiring 2-200 characters; and a deletion-audit tab. It provides no export control and no way to edit content. Register its sidebar entry as `AI 会话审计` with the `ChatLineSquare` icon.

All four admin calls use existing authenticated request handling. Direct route access is guarded by both frontend superuser metadata and backend `require_superuser`.

- [ ] **Step 4: Run audit, route, and build checks**

Run: `cd frontend; npm test -- src/views/system/ai-conversations.test.js src/router/routes.test.js`

Expected: PASS.

Run: `cd frontend; npm run build`

Expected: PASS.

- [ ] **Step 5: Commit the admin audit UI**

```bash
git add frontend/src/views/system/ai-conversations.vue frontend/src/views/system/ai-conversations.test.js frontend/src/api/aiAssistant.js frontend/src/router/index.js frontend/src/layout/index.vue
git commit -m "feat: add AI conversation audit view"
```

### Task 13: Configure Streaming Proxy, Retention Timer, and Production Redis Requirement

**Files:**
- Create: `deploy/sd-scm-ai-cleanup.service`
- Create: `deploy/sd-scm-ai-cleanup.timer`
- Modify: `deploy/nginx.conf`
- Modify: `deploy/sd-scm-backend.service`

**Interfaces:**
- Nginx streams `/api/v1/ai-assistant/conversations/*/messages` without buffering for up to 300 seconds.
- systemd runs cleanup daily at 02:20 Asia/Shanghai with persistent catch-up.
- The two-worker backend starts only with a reachable configured Redis when `AI_SHARED_STORE_REQUIRED=true`.

- [ ] **Step 1: Add an operations configuration assertion script to the verification notes**

Run before edits:

```powershell
Select-String -LiteralPath deploy\nginx.conf -Pattern 'proxy_buffering off','proxy_read_timeout 300s'
```

Expected: no matches, proving streaming configuration is absent.

- [ ] **Step 2: Add the dedicated SSE location and cleanup units**

Place this location before generic `/api/`:

```nginx
location ~ ^/api/v1/ai-assistant/conversations/[0-9]+/messages$ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    gzip off;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
}
```

```ini
# deploy/sd-scm-ai-cleanup.timer
[Unit]
Description=Daily AI conversation retention cleanup

[Timer]
OnCalendar=*-*-* 02:20:00 Asia/Shanghai
Persistent=true
Unit=sd-scm-ai-cleanup.service

[Install]
WantedBy=timers.target
```

The one-shot service uses the same user, group, working directory, environment file, and virtualenv as the backend and runs `python -m app.jobs.cleanup_ai_conversations`.

- [ ] **Step 3: Require shared runtime state in the backend service**

Add `EnvironmentFile=/opt/sd-scm/backend/.env`, `After=redis-server.service`, and `Wants=redis-server.service`. Production `.env` must set a real `REDIS_URL`, `AI_SHARED_STORE_REQUIRED=true`, `AI_CONVERSATION_RETENTION_DAYS=180`, and the DeepSeek settings; never put secrets in the unit or repository.

- [ ] **Step 4: Validate configuration syntax locally**

Run on the Linux production host after copying the candidate site file into its normal include location: `nginx -t`

Expected: `syntax is ok` and `test is successful`; do not reload on failure.

Run on the Linux production host: `systemd-analyze verify /etc/systemd/system/sd-scm-backend.service /etc/systemd/system/sd-scm-ai-cleanup.service /etc/systemd/system/sd-scm-ai-cleanup.timer`

Expected: no unit syntax errors.

- [ ] **Step 5: Commit operations configuration**

```bash
git add deploy/nginx.conf deploy/sd-scm-backend.service deploy/sd-scm-ai-cleanup.service deploy/sd-scm-ai-cleanup.timer
git commit -m "ops: configure AI streaming and retention"
```

### Task 14: Run Security, Browser, Regression, and Production Deployment Gates

**Files:**
- Create: `frontend/playwright.config.js`
- Create: `frontend/e2e/portal-ai.spec.js`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: backend/frontend tests only when a gate reveals a real defect.

**Interfaces:**
- Verifies desktop 1440x900 and mobile 390x844 portal behavior.
- Verifies authenticated streaming, stop, action click, no automatic navigation, and business-card discoverability.
- Verifies unauthorized scenic prompt injection cannot reach analytics queries.
- Deploys one atomic release containing both plans.

- [ ] **Step 1: Install Playwright and write mocked browser journeys**

Run: `cd frontend; npm install --save-dev @playwright/test@^1.55.0`

Add scripts `"test:e2e": "playwright test"` and configure a Vite web server on `127.0.0.1:4173`. The browser test must intercept auth, portal, conversation, suggestion, message-stream, and stop endpoints; inject a valid token before navigation; and cover:

```javascript
test('desktop streams an answer and navigates only after action click', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await authenticateAndMockPortal(page)
  await page.goto('/')
  await expect(page.getByText('山东出版投资有限公司工作平台')).toBeVisible()
  await expect(page.locator('[data-testid="application-entry"]')).toHaveCount(3)
  await page.getByRole('textbox').fill('遵义动物园上个月经营数据')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('2026-07-01 至 2026-07-31')).toBeVisible()
  await expect(page).toHaveURL('/')
  await page.getByRole('button', { name: '前往遵义动物园' }).click()
  await expect(page).toHaveURL('/supplymanagement/cultural-tourism/zunyi-zoo')
})
```

Add a mobile test that opens the conversation drawer, sends/stops a response, scrolls to the application region, and asserts no element crosses the viewport.

- [ ] **Step 2: Run all backend security and integration tests**

Run: `cd backend; python -m unittest tests.test_ai_models tests.test_ai_dates tests.test_scenic_analytics tests.test_ai_tools tests.test_ai_orchestrator tests.test_ai_conversations tests.test_ai_streaming tests.test_company_permissions tests.test_portal_api -v`

Expected: PASS.

Run: `cd backend; python -m unittest discover -s tests -v`

Expected: all backend tests PASS.

- [ ] **Step 3: Run all frontend and browser tests plus the production build**

Run: `cd frontend; npm test`

Expected: all Vitest tests PASS.

Run: `cd frontend; npx playwright install chromium; npm run test:e2e`

Expected: desktop and mobile tests PASS; screenshots show non-overlapping AI controls and visible business-system entries.

Run: `cd frontend; npm run build`

Expected: Vite exits 0.

- [ ] **Step 4: Perform staged production deployment and smoke tests**

Before production mutation:

1. Confirm `git status --short` contains no unintended staged files and push the reviewed commits to GitHub.
2. Back up the production MySQL database and record the backup path.
3. Confirm Redis is installed, reachable locally, persistent as required by operations policy, and not exposed publicly.
4. Apply `20260805_user_company_roles.sql` then `20260805_ai_assistant.sql`; query table counts and the admin backfill.
5. Upload backend/frontend release artifacts to a versioned directory, install locked dependencies, and build frontend.
6. Switch the release symlink, reload systemd, enable the cleanup timer, validate `nginx -t`, and reload Nginx.
7. Call `/api/v1/health`, log in, load `/`, create a conversation, stream a platform answer, stop a scenic answer, click a scenic action, open `/supplymanagement`, and verify old-route redirects.
8. Confirm logs contain request IDs and statuses but not prompts, answers, raw business data, tokens, or model keys.

Expected: two Uvicorn workers are healthy, `ai_shared_store=ready`, the timer is active, SSE begins before completion, all three app cards render, and no existing supply workflow regresses.

- [ ] **Step 5: Commit browser gates and record the released revision**

```bash
git add frontend/playwright.config.js frontend/e2e/portal-ai.spec.js frontend/package.json frontend/package-lock.json
git commit -m "test: cover unified portal AI journeys"
```

Run: `git rev-parse HEAD; git ls-remote origin refs/heads/main`

Expected: local `HEAD`, GitHub `main`, and the deployed release revision are identical.

---

## Final Completion Gate

- [ ] `/` restores the last opened conversation and keeps the three application entries separately visible below it.
- [ ] Users can create, switch, rename, and delete multiple conversations.
- [ ] Platform overview, application status, scenic summary, trend, comparison, and navigation work within authorization.
- [ ] Investment and fund business-data questions state that the corresponding subsystem is under construction and has no queryable data.
- [ ] Every scenic answer shows requested dates, actual data coverage, update time, and partial-coverage status.
- [ ] Prompt injection, arbitrary URLs, unknown tool fields, raw ledgers, attachments, SQL, and internal formulas are rejected before data reaches the model.
- [ ] Streaming emits the documented order, duplicate submissions return 409, stop works across two workers, and disconnected streams settle message state.
- [ ] DeepSeek outage fallback works for controlled intents and free-form questions report temporary unavailability.
- [ ] User deletion, admin deletion with reason, and 180-day cleanup remove content while retaining content-free deletion receipts.
- [ ] The sole information maintainer can audit/delete conversations; ordinary users cannot access admin APIs or the audit route.
- [ ] Nginx buffering is disabled for the message stream, Redis shared state is required in production, and daily cleanup is active.
- [ ] Full backend tests, frontend tests, desktop/mobile browser tests, production build, GitHub push, migration, deployment, and smoke checks pass.
