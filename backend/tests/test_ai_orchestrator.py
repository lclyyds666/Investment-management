import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.schemas.ai_assistant import ScenicNavigationAction, ToolResult
from app.services.ai_orchestrator import (
    AiOrchestrator,
    _UNAVAILABLE,
    _allowed_scenics,
    _local_intent,
    _validate_decision,
    is_safe_model_text,
)
from app.services.deepseek_chat import IntentDecision
from app.services.scenic_config import SCENIC_SEEDS


def _seed_configs():
    return [
        SimpleNamespace(scenic_id=item[0], scenic_name=item[1])
        for item in SCENIC_SEEDS
    ]


class OfflineClient:
    async def classify(self, *args, **kwargs):
        raise RuntimeError("offline")

    async def stream_answer(self, *args, **kwargs):
        raise RuntimeError("offline")
        yield ""


class PoisonedAnswerClient:
    def __init__(self, answer, decision=None):
        self.answer = answer
        self.decision = decision or IntentDecision(intent="free_form")
        self.classify_calls = 0
        self.stream_calls = 0

    async def classify(self, *args, **kwargs):
        self.classify_calls += 1
        return self.decision

    async def stream_answer(self, *args, **kwargs):
        self.stream_calls += 1
        yield self.answer


class AiOrchestratorTest(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.ai_orchestrator.list_effective_configs")
    def test_custom_effective_scenic_name_canonicalizes_to_route_safe_id(self, list_configs):
        list_configs.return_value = [
            SimpleNamespace(scenic_id="custom-museum-2026", scenic_name="Custom Museum"),
            SimpleNamespace(scenic_id="Unsafe/Scenic", scenic_name="Unsafe"),
        ]
        context = Mock()
        allowed = _allowed_scenics(context)
        self.assertEqual(allowed, [{
            "scenic_id": "custom-museum-2026", "scenic_name": "Custom Museum"
        }])
        local = _local_intent("打开 Custom Museum", context)
        self.assertEqual(local.scenic_ids, ["custom-museum-2026"])
        decision = _validate_decision(
            IntentDecision(intent="scenic_navigation", scenic_ids=["custom museum"]), context
        )
        self.assertEqual(decision.scenic_ids, ["custom-museum-2026"])

    def test_standalone_helpers_are_the_only_seed_fallback(self):
        self.assertTrue(_allowed_scenics(None))
        with patch(
            "app.services.ai_orchestrator.list_effective_configs",
            side_effect=RuntimeError("config unavailable"),
        ):
            self.assertEqual(_allowed_scenics(Mock()), [])

    def test_navigation_action_requires_route_safe_scenic_id(self):
        action = ScenicNavigationAction(
            scenic_id="dynamic--scenic-2026", label="Dynamic scenic"
        )
        self.assertEqual(action.scenic_id, "dynamic--scenic-2026")
        for scenic_id in (
            "-leading",
            "trailing-",
            "../admin",
            "https://evil.example",
            "Uppercase",
        ):
            with self.subTest(scenic_id=scenic_id):
                with self.assertRaises(ValueError):
                    ScenicNavigationAction(scenic_id=scenic_id, label="Unsafe")

    @patch("app.services.ai_orchestrator.execute_tool")
    async def test_failed_or_empty_config_registry_never_runs_scenic_tool(self, execute_tool):
        client = PoisonedAnswerClient(
            "unused",
            decision=IntentDecision(
                intent="scenic_navigation", scenic_ids=["zunyi-zoo"]
            ),
        )
        for config_result in (RuntimeError("config unavailable"), []):
            with self.subTest(config_result=config_result):
                execute_tool.reset_mock()
                config_patch = (
                    patch(
                        "app.services.ai_orchestrator.list_effective_configs",
                        side_effect=config_result,
                    )
                    if isinstance(config_result, Exception)
                    else patch(
                        "app.services.ai_orchestrator.list_effective_configs",
                        return_value=config_result,
                    )
                )
                with config_patch:
                    events = [
                        event
                        async for event in AiOrchestrator(client=client).stream(
                            "打开遵义动物园", Mock()
                        )
                    ]
                execute_tool.assert_not_called()
                self.assertFalse(any(event.kind == "action" for event in events))
                self.assertEqual(
                    "".join(event.payload.get("text", "") for event in events),
                    _UNAVAILABLE,
                )

    def test_defensive_scanner_rejects_adversarial_provider_text(self):
        adversarial_text = (
            "example.com/private",
            "//internal.example/private",
            "PRAGMA table_info(biz_ticket_ledger);",
            "WITH rows AS (SELECT * FROM records) SELECT * FROM rows;",
            "CALL private_report()",
            "EXECUTE private_report",
            "The internal formula is sales divided by count.",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
            "ghp_abcdefghijklmnopqrstuvwxyz123456",
            '{"id":1,"name":"alpha","amount":100}',
        )

        for provider_text in adversarial_text:
            with self.subTest(provider_text=provider_text):
                self.assertFalse(is_safe_model_text(provider_text))

    async def test_platform_overview_works_without_deepseek(self):
        orchestrator = AiOrchestrator(client=OfflineClient())
        events = [
            event async for event in orchestrator.stream("这个平台是干什么的？", Mock())
        ]
        text = "".join(event.payload.get("text", "") for event in events)
        self.assertIn("山东出版投资有限公司工作平台", text)
        self.assertIn("供应链管理", text)

    async def test_free_form_reports_unavailable_when_model_is_offline(self):
        orchestrator = AiOrchestrator(client=OfflineClient())
        events = [event async for event in orchestrator.stream("写一首诗", Mock())]
        text = "".join(event.payload.get("text", "") for event in events)
        self.assertIn("AI 服务暂时不可用，请稍后重试。", text)

    @patch("app.services.ai_orchestrator.list_effective_configs")
    @patch("app.services.ai_orchestrator.execute_tool")
    async def test_tool_answer_uses_local_aggregate_without_provider_stream(
        self, execute_tool, list_configs
    ):
        list_configs.return_value = _seed_configs()
        execute_tool.return_value = ToolResult(data={"summaries": [{
            "scenic_name": "遵义动物园",
            "sales": "870.00",
            "writeoff_count": 10,
            "writeoff_rate": "80.0",
        }]})
        client = PoisonedAnswerClient("SELECT * FROM biz_ticket_ledger。")
        events = [event async for event in AiOrchestrator(client=client).stream(
            "遵义动物园上月数据", Mock()
        )]

        text = "".join(event.payload.get("text", "") for event in events)
        self.assertIn("870.00", text)
        self.assertNotIn("SELECT", text)
        self.assertEqual(client.stream_calls, 0)
        self.assertTrue(all(
            event.payload.get("engine") in (None, "local") for event in events
        ))

    @patch("app.services.ai_orchestrator.list_effective_configs")
    @patch("app.services.ai_orchestrator.execute_tool")
    async def test_navigation_action_survives_model_outage(
        self, execute_tool, list_configs
    ):
        list_configs.return_value = _seed_configs()
        execute_tool.return_value = ToolResult(actions=[ScenicNavigationAction(
            scenic_id="zunyi-zoo", label="前往遵义动物园"
        )])
        events = [event async for event in AiOrchestrator(
            client=OfflineClient()
        ).stream("打开遵义动物园", Mock())]
        actions = [event.payload for event in events if event.kind == "action"]
        self.assertEqual(actions[0]["scenic_id"], "zunyi-zoo")
        self.assertNotIn("url", actions[0])

    @patch("app.services.ai_orchestrator.list_effective_configs")
    @patch("app.services.ai_orchestrator.execute_tool")
    async def test_scenic_tool_status_carries_persistable_coverage_metadata(
        self, execute_tool, list_configs
    ):
        list_configs.return_value = _seed_configs()
        execute_tool.return_value = ToolResult(data={"summaries": [{
            "requested_start": "2026-07-01",
            "requested_end": "2026-07-31",
            "covered_start": "2026-07-02",
            "covered_end": "2026-07-30",
            "data_updated_at": "2026-08-01T09:30:00",
        }]})
        events = [event async for event in AiOrchestrator(
            client=OfflineClient()
        ).stream("遵义动物园上月数据", Mock())]
        completed = next(
            event for event in events
            if event.kind == "tool.status" and event.payload["status"] == "completed"
        )
        self.assertEqual(completed.payload["metadata"]["data_start_date"], "2026-07-01")
        self.assertEqual(completed.payload["metadata"]["data_updated_at"], "2026-08-01T09:30:00")

    async def test_free_form_never_calls_provider_answer_stream_for_adversarial_output(self):
        adversarial_answers = (
            "example.com/private",
            "//internal.example/private",
            "PRAGMA table_info(biz_ticket_ledger);",
            "WITH rows AS (SELECT * FROM biz_ticket_ledger) SELECT * FROM rows;",
            "The internal formula is sales divided by count.",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
            "ghp_abcdefghijklmnopqrstuvwxyz123456",
            '{"id":1,"customer_name":"secret","daily_amount":100}',
        )
        for provider_text in adversarial_answers:
            with self.subTest(provider_text=provider_text):
                client = PoisonedAnswerClient(provider_text)
                events = [event async for event in AiOrchestrator(client=client).stream(
                    "\u5e2e\u6211\u603b\u7ed3", Mock()
                )]

                text = "".join(event.payload.get("text", "") for event in events)
                self.assertEqual(text, _UNAVAILABLE)
                self.assertNotIn(provider_text, text)
                self.assertEqual(client.classify_calls, 1)
                self.assertEqual(client.stream_calls, 0)

    async def test_even_safe_free_form_provider_answer_is_not_requested(self):
        client = PoisonedAnswerClient("\u8fd9\u662f\u4e00\u6bb5\u5b89\u5168\u7684\u6587\u672c\u3002")
        events = [event async for event in AiOrchestrator(client=client).stream(
            "\u5e2e\u6211\u603b\u7ed3", Mock()
        )]

        text = "".join(event.payload.get("text", "") for event in events)
        self.assertEqual(text, _UNAVAILABLE)
        self.assertEqual(client.stream_calls, 0)


if __name__ == "__main__":
    unittest.main()
