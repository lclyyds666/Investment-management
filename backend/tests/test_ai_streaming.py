import asyncio
import json
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.ai_assistant import stop_message, stream_message
from app.api.v1.endpoints.health import health_check
from app.core import store
from app.models.ai_assistant import AiConversation, AiMessage, AiToolCall
from app.schemas.ai_assistant import AiMessageCreate
from app.services import ai_runtime
from app.services.ai_conversations import encode_sse
from app.services.ai_orchestrator import OrchestratorEvent, _UNAVAILABLE


def _event(frame: str) -> tuple[str, dict]:
    lines = frame.splitlines()
    return lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))


class _ConnectedRequest:
    async def is_disconnected(self):
        return False


class _DisconnectAfterFirstChunk:
    def __init__(self):
        self.checks = 0

    async def is_disconnected(self):
        self.checks += 1
        return self.checks > 1


class _CompletedOrchestrator:
    async def stream(self, question, context):
        context.db.add(AiToolCall(
            message_id=context.message_id,
            tool_name="get_scenic_summary",
            arguments_json={
                "scenic_ids": ["zunyi-zoo"],
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
            },
            permission_decision="allowed",
            status="completed",
            duration_ms=3,
            result_summary_json={"result_count": 1},
        ))
        yield OrchestratorEvent(
            "tool.status", {"tool": "get_scenic_summary", "status": "running"}
        )
        yield OrchestratorEvent(
            "tool.status", {
                "tool": "get_scenic_summary",
                "status": "completed",
                "metadata": {
                    "data_start_date": "2026-07-01",
                    "data_end_date": "2026-07-31",
                    "data_covered_start": "2026-07-02",
                    "data_covered_end": "2026-07-30",
                    "data_updated_at": "2026-08-01T09:30:00",
                },
            },
        )
        yield OrchestratorEvent(
            "text.delta", {"text": "遵义经营数据", "engine": "local"}
        )
        yield OrchestratorEvent("action", {
            "type": "navigate_to_scenic",
            "scenic_id": "zunyi-zoo",
            "label": "前往遵义动物园",
        })


class _TwoDeltaOrchestrator:
    async def stream(self, question, context):
        yield OrchestratorEvent("text.delta", {"text": "第一段", "engine": "local"})
        yield OrchestratorEvent("text.delta", {"text": "第二段", "engine": "local"})


class _OneDeltaOrchestrator:
    async def stream(self, question, context):
        yield OrchestratorEvent("text.delta", {"text": "唯一一段", "engine": "local"})


class _SplitUntrustedOrchestrator:
    def __init__(self, engine):
        self.engine = engine

    async def stream(self, question, context):
        yield OrchestratorEvent("text.delta", {"text": "https", "engine": self.engine})
        yield OrchestratorEvent(
            "text.delta", {"text": "://example.com.", "engine": self.engine}
        )


class AiSseContractTest(unittest.TestCase):
    def test_sse_frame_has_event_and_single_json_data_line(self):
        frame = encode_sse("text.delta", {"request_id": "r1", "text": "遵义"})
        self.assertEqual(
            frame,
            'event: text.delta\ndata: {"request_id":"r1","text":"遵义"}\n\n',
        )

    def test_terminal_events_are_explicit(self):
        self.assertIn("message.completed", {"message.completed", "message.stopped", "error"})


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

    def test_user_can_run_only_configured_number_of_generations(self):
        with patch.object(ai_runtime.settings, "AI_MAX_CONCURRENT_PER_USER", 2):
            first = ai_runtime.acquire_generation(3, 10, "request-a")
            second = ai_runtime.acquire_generation(3, 11, "request-b")
            with self.assertRaises(HTTPException) as raised:
                ai_runtime.acquire_generation(3, 12, "request-c")
            self.assertEqual(raised.exception.status_code, 429)
            ai_runtime.release_generation(first)
            ai_runtime.release_generation(second)

    def test_submission_rate_is_limited(self):
        with patch.object(ai_runtime.settings, "AI_REQUESTS_PER_MINUTE", 2):
            ai_runtime.check_submission_rate(3)
            ai_runtime.check_submission_rate(3)
            with self.assertRaises(HTTPException) as raised:
                ai_runtime.check_submission_rate(3)
            self.assertEqual(raised.exception.status_code, 429)

    def test_stale_release_does_not_delete_reacquired_lease(self):
        old_lease = ai_runtime.acquire_generation(3, 10, "request-a")
        conversation_key = "ai:conversation:10:lease"
        ai_runtime.runtime_store.delete(conversation_key)
        ai_runtime.runtime_store.remove_member("ai:user:3:active", "request-a")

        current_lease = ai_runtime.acquire_generation(3, 10, "request-b")
        ai_runtime.release_generation(old_lease)

        self.assertEqual(ai_runtime.runtime_store.get(conversation_key), "request-b")
        ai_runtime.release_generation(current_lease)

    def test_health_reports_only_shared_store_readiness(self):
        response = health_check()
        self.assertEqual(set(response.data), {"status", "ai_shared_store"})
        self.assertIn(response.data["ai_shared_store"], {"ready", "not_configured"})

    def test_required_shared_store_rejects_memory_backend(self):
        with patch.object(store.settings, "AI_SHARED_STORE_REQUIRED", True):
            with self.assertRaises(RuntimeError):
                store.validate_shared_store_requirement()


class AiStreamingEndpointTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ai_runtime.reset_for_tests()
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        AiConversation.__table__.create(self.engine)
        AiMessage.__table__.create(self.engine)
        AiToolCall.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.user = SimpleNamespace(id=7, is_superuser=False)
        self.conversation = AiConversation(
            owner_id=self.user.id,
            title="新会话",
            status="active",
            last_active_at=datetime(2026, 8, 5, 10, 0),
            expires_at=datetime(2027, 2, 1, 10, 0),
        )
        self.db.add(self.conversation)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        ai_runtime.reset_for_tests()

    async def _stream(self, content, orchestrator, request=None):
        payload = AiMessageCreate(content=content, client_message_id=uuid4())
        with patch(
            "app.services.ai_conversations.AiOrchestrator", return_value=orchestrator
        ):
            response = await stream_message(
                conversation_id=self.conversation.id,
                payload=payload,
                request=request or _ConnectedRequest(),
                db=self.db,
                current_user=self.user,
            )
            frames = [frame async for frame in response.body_iterator]
        return response, [_event(frame) for frame in frames]

    async def test_duplicate_submission_returns_409_without_another_user_message(self):
        client_message_id = uuid4()
        self.db.add(AiMessage(
            conversation_id=self.conversation.id,
            role="user",
            content="原始问题",
            status="completed",
            client_message_id=str(client_message_id),
            request_id="existing-request",
        ))
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            await stream_message(
                conversation_id=self.conversation.id,
                payload=AiMessageCreate(
                    content="网络重试",
                    client_message_id=client_message_id,
                ),
                request=_ConnectedRequest(),
                db=self.db,
                current_user=self.user,
            )

        self.assertEqual(raised.exception.status_code, 409)
        count = self.db.scalar(
            select(func.count()).select_from(AiMessage).where(AiMessage.role == "user")
        )
        self.assertEqual(count, 1)

    async def test_completed_stream_orders_events_and_persists_lifecycle(self):
        response, events = await self._stream("遵义经营数据", _CompletedOrchestrator())

        names = [name for name, _ in events]
        self.assertEqual(names, [
            "message.created",
            "tool.status",
            "tool.status",
            "text.delta",
            "action",
            "message.completed",
        ])
        self.assertEqual(sum(name in {"message.completed", "message.stopped", "error"}
                             for name in names), 1)
        self.assertEqual(response.media_type, "text/event-stream")
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        request_id = response.headers["x-request-id"]
        UUID(request_id)
        self.assertTrue(all(payload["request_id"] == request_id for _, payload in events))

        self.db.expire_all()
        assistant = self.db.scalar(select(AiMessage).where(AiMessage.role == "assistant"))
        self.assertEqual(assistant.status, "completed")
        self.assertEqual(assistant.content, "遵义经营数据")
        self.assertEqual(assistant.request_id, request_id)
        self.assertEqual(assistant.engine, "local")
        self.assertIsNotNone(assistant.first_token_ms)
        self.assertIsNotNone(assistant.duration_ms)
        self.assertEqual(assistant.data_start_date, date(2026, 7, 1))
        self.assertEqual(assistant.data_end_date, date(2026, 7, 31))
        self.assertEqual(assistant.data_covered_start, date(2026, 7, 2))
        self.assertEqual(assistant.data_covered_end, date(2026, 7, 30))
        self.assertEqual(assistant.data_updated_at, datetime(2026, 8, 1, 9, 30))
        self.assertEqual(assistant.actions_json[0]["scenic_id"], "zunyi-zoo")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AiToolCall)), 1)
        conversation = self.db.get(AiConversation, self.conversation.id)
        self.assertEqual(conversation.title, "遵义经营数据")
        self.assertEqual(
            conversation.expires_at - conversation.last_active_at,
            timedelta(days=180),
        )

    async def test_untrusted_split_deltas_never_reach_sse_or_persistence(self):
        for engine in ("deepseek", "local-copy"):
            with self.subTest(engine=engine):
                _, events = await self._stream(
                    "untrusted output", _SplitUntrustedOrchestrator(engine)
                )

                self.assertEqual([name for name, _ in events], [
                    "message.created", "text.delta", "message.completed",
                ])
                deltas = [payload["text"] for name, payload in events if name == "text.delta"]
                self.assertEqual(deltas, [_UNAVAILABLE])
                serialized = json.dumps(events, ensure_ascii=False)
                self.assertNotIn("https", serialized)
                self.assertNotIn("example.com", serialized)

                self.db.expire_all()
                assistant = self.db.scalar(
                    select(AiMessage)
                    .where(AiMessage.role == "assistant")
                    .order_by(AiMessage.id.desc())
                )
                self.assertEqual(assistant.content, _UNAVAILABLE)
                self.assertEqual(assistant.engine, "local")

    async def test_stop_flag_after_delta_emits_stopped_terminal_and_releases_lease(self):
        payload = AiMessageCreate(content="分段回答", client_message_id=uuid4())
        with patch(
            "app.services.ai_conversations.AiOrchestrator",
            return_value=_OneDeltaOrchestrator(),
        ):
            response = await stream_message(
                conversation_id=self.conversation.id,
                payload=payload,
                request=_ConnectedRequest(),
                db=self.db,
                current_user=self.user,
            )
            events = []
            async for frame in response.body_iterator:
                event = _event(frame)
                events.append(event)
                if event[0] == "text.delta":
                    ai_runtime.request_stop(event[1]["message_id"])

        self.assertEqual([name for name, _ in events], [
            "message.created", "text.delta", "message.stopped",
        ])
        self.db.expire_all()
        assistant = self.db.scalar(select(AiMessage).where(AiMessage.role == "assistant"))
        self.assertEqual(assistant.status, "stopped")
        self.assertEqual(assistant.content, "唯一一段")
        lease = ai_runtime.acquire_generation(
            self.user.id, self.conversation.id, "subsequent-request"
        )
        ai_runtime.release_generation(lease)

    async def test_disconnect_after_delta_settles_message_as_stopped(self):
        _, events = await self._stream(
            "断开连接", _TwoDeltaOrchestrator(), _DisconnectAfterFirstChunk()
        )

        self.assertEqual([name for name, _ in events], [
            "message.created", "text.delta", "message.stopped",
        ])
        self.db.expire_all()
        assistant = self.db.scalar(select(AiMessage).where(AiMessage.role == "assistant"))
        self.assertEqual(assistant.status, "stopped")

    async def test_closing_stream_after_created_settles_and_releases_lease(self):
        payload = AiMessageCreate(content="关闭连接", client_message_id=uuid4())
        with patch(
            "app.services.ai_conversations.AiOrchestrator",
            return_value=_TwoDeltaOrchestrator(),
        ):
            response = await stream_message(
                conversation_id=self.conversation.id,
                payload=payload,
                request=_ConnectedRequest(),
                db=self.db,
                current_user=self.user,
            )
            first = await anext(response.body_iterator)
            self.assertEqual(_event(first)[0], "message.created")
            await response.body_iterator.aclose()

        self.db.expire_all()
        assistant = self.db.scalar(select(AiMessage).where(AiMessage.role == "assistant"))
        self.assertEqual(assistant.status, "stopped")
        lease = ai_runtime.acquire_generation(
            self.user.id, self.conversation.id, "subsequent-request"
        )
        ai_runtime.release_generation(lease)

    async def test_task_cancellation_settles_releases_and_propagates(self):
        payload = AiMessageCreate(content="取消任务", client_message_id=uuid4())
        with patch(
            "app.services.ai_conversations.AiOrchestrator",
            return_value=_TwoDeltaOrchestrator(),
        ):
            response = await stream_message(
                conversation_id=self.conversation.id,
                payload=payload,
                request=_ConnectedRequest(),
                db=self.db,
                current_user=self.user,
            )
            first = await anext(response.body_iterator)
            self.assertEqual(_event(first)[0], "message.created")
            with self.assertRaises(asyncio.CancelledError):
                await response.body_iterator.athrow(asyncio.CancelledError())

        self.db.expire_all()
        assistant = self.db.scalar(select(AiMessage).where(AiMessage.role == "assistant"))
        self.assertEqual(assistant.status, "stopped")
        lease = ai_runtime.acquire_generation(
            self.user.id, self.conversation.id, "subsequent-request"
        )
        ai_runtime.release_generation(lease)

    async def test_stop_endpoint_checks_owner_and_preserves_terminal_status(self):
        terminal = AiMessage(
            conversation_id=self.conversation.id,
            role="assistant",
            content="完成",
            status="completed",
            request_id="terminal-request",
        )
        self.db.add(terminal)
        self.db.commit()

        response = stop_message(terminal.id, self.db, self.user)
        self.assertEqual(response.data, {"id": terminal.id, "status": "completed"})
        self.assertFalse(ai_runtime.is_stop_requested(terminal.id))

        other_conversation = AiConversation(
            owner_id=99,
            title="他人会话",
            status="active",
            last_active_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=180),
        )
        self.db.add(other_conversation)
        self.db.flush()
        foreign = AiMessage(
            conversation_id=other_conversation.id,
            role="assistant",
            content="",
            status="generating",
            request_id="foreign-request",
        )
        self.db.add(foreign)
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            stop_message(foreign.id, self.db, self.user)
        self.assertEqual(raised.exception.status_code, 404)
        self.assertFalse(ai_runtime.is_stop_requested(foreign.id))


if __name__ == "__main__":
    unittest.main()
