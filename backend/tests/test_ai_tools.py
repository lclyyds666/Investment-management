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
