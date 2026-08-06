import unittest
from unittest.mock import Mock, patch

from app.schemas.ai_assistant import ToolResult
from app.services.ai_orchestrator import AiOrchestrator, _UNAVAILABLE
from app.services.deepseek_chat import IntentDecision


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


class ChunkClient:
    def __init__(self, chunks, decision=None):
        self.chunks = chunks
        self.decision = decision or IntentDecision(intent="free_form")

    async def classify(self, *args, **kwargs):
        return self.decision

    async def stream_answer(self, *args, **kwargs):
        for chunk in self.chunks:
            yield chunk


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

    async def test_free_form_rejects_url_split_across_model_chunks(self):
        events = [event async for event in AiOrchestrator(client=ChunkClient([
            "\u8bf7\u8bbf\u95ee https", "://example.com \u83b7\u53d6\u66f4\u591a\u4fe1\u606f\u3002",
        ])).stream("\u5e2e\u6211\u603b\u7ed3", Mock())]

        text = "".join(event.payload.get("text", "") for event in events)
        self.assertEqual(text, _UNAVAILABLE)
        self.assertNotIn("https", text)
        self.assertTrue(all(event.payload.get("engine") != "deepseek" for event in events))

    async def test_free_form_rejects_sql_and_internal_formula(self):
        for model_text in (
            "SELECT * FROM biz_ticket_ledger\u3002",
            "\u6838\u9500\u7387=\u6838\u9500\u6570\u91cf/\u9500\u552e\u6570\u91cf\u3002",
        ):
            with self.subTest(model_text=model_text):
                events = [event async for event in AiOrchestrator(
                    client=ChunkClient([model_text[:4], model_text[4:]])
                ).stream("\u5e2e\u6211\u603b\u7ed3", Mock())]
                text = "".join(event.payload.get("text", "") for event in events)
                self.assertEqual(text, _UNAVAILABLE)
                self.assertNotIn(model_text, text)

    @patch("app.services.ai_orchestrator.execute_tool")
    async def test_data_answer_rejects_raw_ledger_reference_without_emitting_it(self, execute_tool):
        execute_tool.return_value = ToolResult(data={"summaries": []})
        events = [event async for event in AiOrchestrator(client=ChunkClient([
            "\u539f\u59cb\u53f0\u8d26\u660e", "\u7ec6\u4f4d\u4e8e daily_json\u3002",
        ])).stream("\u9075\u4e49\u52a8\u7269\u56ed\u4e0a\u6708\u6570\u636e", Mock())]

        text = "".join(event.payload.get("text", "") for event in events)
        self.assertEqual(text, _UNAVAILABLE)
        self.assertNotIn("daily_json", text)

    async def test_safe_complete_segments_are_emitted_in_order(self):
        events = [event async for event in AiOrchestrator(client=ChunkClient([
            "\u5e73\u53f0\u4ec5\u63d0\u4f9b\u6c47\u603b", "\u7ecf\u8425\u6570\u636e\u3002", "\u53ef\u6309\u6761\u4ef6\u67e5\u8be2\u3002",
        ])).stream("\u5e2e\u6211\u603b\u7ed3", Mock())]

        deltas = [event.payload for event in events if event.kind == "text.delta"]
        self.assertEqual([item["text"] for item in deltas], [
            "\u5e73\u53f0\u4ec5\u63d0\u4f9b\u6c47\u603b\u7ecf\u8425\u6570\u636e\u3002", "\u53ef\u6309\u6761\u4ef6\u67e5\u8be2\u3002",
        ])
        self.assertTrue(all(item["engine"] == "deepseek" for item in deltas))

    async def test_incomplete_model_output_falls_back_without_emitting_it(self):
        events = [event async for event in AiOrchestrator(
            client=ChunkClient(["\u672a\u7ed3\u675f\u7684\u6a21\u578b\u56de\u7b54"])
        ).stream("\u5e2e\u6211\u603b\u7ed3", Mock())]

        text = "".join(event.payload.get("text", "") for event in events)
        self.assertEqual(text, _UNAVAILABLE)
        self.assertNotIn("\u672a\u7ed3\u675f\u7684\u6a21\u578b\u56de\u7b54", text)

    async def test_free_form_rejects_credentials_attachment_and_database_structure(self):
        for model_text in (
            "Bearer secret-token\u3002",
            "attachment content\u3002",
            "database table names\u3002",
            "SUM(sales)/COUNT(rows)\u3002",
        ):
            with self.subTest(model_text=model_text):
                events = [event async for event in AiOrchestrator(
                    client=ChunkClient([model_text])
                ).stream("\u5e2e\u6211\u603b\u7ed3", Mock())]
                text = "".join(event.payload.get("text", "") for event in events)
                self.assertEqual(text, _UNAVAILABLE)
                self.assertNotIn(model_text, text)


if __name__ == "__main__":
    unittest.main()
