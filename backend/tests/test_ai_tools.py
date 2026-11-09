import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app.services.ai_tools import TOOL_REGISTRY, ToolContext, execute_tool


class AiToolSecurityTest(unittest.TestCase):
    def test_registry_contains_only_approved_tools(self):
        self.assertEqual(set(TOOL_REGISTRY), {
            "get_platform_overview", "get_portal_applications", "get_scenic_summary",
            "get_scenic_trend", "compare_scenics", "create_scenic_navigation_action",
        })

    def test_navigation_rejects_arbitrary_url(self):
        context = ToolContext(
            db=Mock(), user=SimpleNamespace(id=2, is_superuser=False), request_id="r1"
        )
        with self.assertRaises(ValidationError):
            execute_tool("create_scenic_navigation_action", {
                "scenic_id": "zunyi-zoo", "url": "https://example.com",
            }, context)

    @patch("app.services.ai_tools.has_resource", return_value=False)
    def test_scenic_query_stops_before_database_access(self, denied):
        db = Mock()
        context = ToolContext(
            db=db, user=SimpleNamespace(id=2, is_superuser=False), request_id="r2"
        )
        with self.assertRaises(PermissionError):
            execute_tool("get_scenic_summary", {
                "scenic_ids": ["zunyi-zoo"],
                "start_date": "2026-07-01", "end_date": "2026-07-31",
            }, context)
        db.scalars.assert_not_called()

    @patch("app.services.ai_tools.has_resource", return_value=True)
    @patch("app.services.ai_tools.list_effective_configs")
    def test_navigation_resolves_name_to_canonical_id_without_url(self, configs, allowed):
        configs.return_value = [SimpleNamespace(
            scenic_id="zunyi-zoo", scenic_name="遵义动物园"
        )]
        context = ToolContext(
            db=Mock(), user=SimpleNamespace(id=2, is_superuser=False), request_id="r3"
        )
        result = execute_tool(
            "create_scenic_navigation_action", {"scenic_id": "遵义动物园"}, context
        )
        action = result.actions[0].model_dump()
        self.assertEqual(action["scenic_id"], "zunyi-zoo")
        self.assertNotIn("url", action)

    def test_unknown_tool_is_rejected(self):
        with self.assertRaises(ValueError):
            execute_tool("run_sql", {}, ToolContext(
                db=Mock(), user=SimpleNamespace(id=2), request_id="r4"
            ))


if __name__ == "__main__":
    unittest.main()


class OperationInsightsTests(unittest.TestCase):
    def test_sanitizer_excludes_identifiers_and_free_text(self):
        from app.schemas.operation_forecast import ForecastOut, ForecastLine
        from app.services.operation_insights import sanitize_aggregate_result
        from datetime import date
        result = ForecastOut(start_date=date(2026, 9, 1), end_date=date(2026, 9, 1), lines=[
            ForecastLine(scenic_id="private-client", business_type="ticket", platform="secret", reasons=["private text"], forecast=100)
        ])
        sanitized = str(sanitize_aggregate_result(result))
        self.assertNotIn("private", sanitized)
        self.assertNotIn("secret", sanitized)
        self.assertIn("100", sanitized)

    def test_llm_failure_and_malformed_output_fall_back(self):
        from datetime import date
        from app.schemas.operation_forecast import ForecastOut
        from app.services.operation_insights import render_operation_insights
        result = ForecastOut(start_date=date(2026, 9, 1), end_date=date(2026, 9, 1))
        with patch("app.services.operation_insights.settings", SimpleNamespace(AI_ENABLED=True, DEEPSEEK_API_KEY="test", DEEPSEEK_MODEL="test")), patch("openai.OpenAI") as client:
            client.return_value.chat.completions.create.side_effect = RuntimeError("offline")
            self.assertEqual(render_operation_insights(result)["engine"], "rules")
            client.return_value.chat.completions.create.side_effect = None
            client.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"summary": "ok", "recommendations": 42}'))])
            self.assertEqual(render_operation_insights(result)["engine"], "rules")
