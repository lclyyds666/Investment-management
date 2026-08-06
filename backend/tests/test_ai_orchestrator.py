import unittest
from unittest.mock import Mock, patch

from app.schemas.ai_assistant import ToolResult
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

    @patch("app.services.ai_orchestrator.execute_tool")
    async def test_model_context_contains_aggregate_result_not_ledger_rows(self, execute_tool):
        execute_tool.return_value = ToolResult(
            data={"sales": "870.00", "writeoff_count": 10}
        )
        client = RecordingClient()
        orchestrator = AiOrchestrator(client=client)
        _ = [
            event async for event in orchestrator.stream("遵义动物园上月数据", Mock())
        ]
        self.assertIn("870.00", client.context)
        self.assertNotIn("daily_json", client.context)
        self.assertNotIn("source_file", client.context)
        self.assertNotIn("遵义动物园上月数据", client.context)

    @patch("app.services.ai_orchestrator.execute_tool")
    async def test_navigation_action_survives_model_outage(self, execute_tool):
        from app.schemas.ai_assistant import ScenicNavigationAction

        execute_tool.return_value = ToolResult(actions=[ScenicNavigationAction(
            scenic_id="zunyi-zoo", label="前往遵义动物园"
        )])
        events = [event async for event in AiOrchestrator(
            client=OfflineClient()
        ).stream("打开遵义动物园", Mock())]
        actions = [event.payload for event in events if event.kind == "action"]
        self.assertEqual(actions[0]["scenic_id"], "zunyi-zoo")
        self.assertNotIn("url", actions[0])

    @patch("app.services.ai_orchestrator.execute_tool")
    async def test_scenic_tool_status_carries_persistable_coverage_metadata(self, execute_tool):
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


if __name__ == "__main__":
    unittest.main()
