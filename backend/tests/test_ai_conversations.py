import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.ai_assistant import router
from app.jobs.cleanup_ai_conversations import run_cleanup
from app.models.ai_assistant import AiConversation, AiDeletionAudit, AiMessage, AiToolCall
from app.schemas.ai_assistant import AdminAiConversationOut
from app.services.ai_conversations import (
    CleanupResult,
    cleanup_expired_conversations,
    delete_admin_conversation,
    get_admin_conversation,
    get_owned_conversation,
    list_admin_conversations,
    suggestions_for_user,
)


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
            "这个平台是干什么的？",
            "介绍一下三个业务系统的建设情况。",
        ])

    @patch("app.services.ai_conversations.has_resource", return_value=True)
    def test_scenic_permission_adds_aggregate_prompts(self, allowed):
        questions = suggestions_for_user(Mock(), SimpleNamespace(is_superuser=False))
        self.assertIn("遵义动物园上个月经营数据。", questions)
        self.assertIn("对比遵义动物园和南阳森林野生动物世界今年经营数据。", questions)


class AiRetentionTest(unittest.TestCase):
    @patch("app.services.ai_conversations.settings.AI_CONVERSATION_RETENTION_DAYS", 90)
    def test_changed_retention_applies_to_existing_conversations(self):
        now = datetime(2026, 8, 5, 1, 0)
        db = Mock()
        stale = SimpleNamespace(
            id=5,
            owner_id=2,
            last_active_at=now - timedelta(days=91),
            messages=[1, 2],
        )
        db.scalars.return_value.all.return_value = [stale]

        result = cleanup_expired_conversations(db, now=now)

        self.assertEqual(result.deleted_conversations, 1)
        self.assertEqual(result.deleted_messages, 2)
        receipt = db.add.call_args.args[0]
        self.assertEqual(receipt.mode, "retention")
        self.assertEqual(receipt.reason, "超过当前会话保留期")

    def test_admin_delete_requires_a_visible_reason(self):
        from app.schemas.ai_assistant import AdminDeleteRequest

        for reason in ("", "  "):
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                AdminDeleteRequest(reason=reason)


class AiAdminConversationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        AiConversation.__table__.create(self.engine)
        AiMessage.__table__.create(self.engine)
        AiToolCall.__table__.create(self.engine)
        AiDeletionAudit.__table__.create(self.engine)
        self.db = Session(self.engine)
        now = datetime(2026, 8, 5, 10, 0)
        self.conversation = AiConversation(
            owner_id=7,
            title="审计会话",
            status="active",
            last_active_at=now,
            expires_at=now + timedelta(days=180),
        )
        self.db.add(self.conversation)
        self.db.flush()
        self.message = AiMessage(
            conversation_id=self.conversation.id,
            role="assistant",
            content="可查询的关键字",
            status="completed",
            request_id="request-1",
            actions_json=[{
                "type": "navigate_to_scenic",
                "scenic_id": "zunyi-zoo",
                "label": "前往遵义动物园",
            }],
        )
        self.db.add(self.message)
        self.db.flush()
        self.db.add(AiToolCall(
            message_id=self.message.id,
            tool_name="get_scenic_summary",
            arguments_json={"scenic_ids": ["zunyi-zoo"]},
            permission_decision="allowed",
            status="completed",
            duration_ms=3,
            result_summary_json={"result_count": 1},
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_admin_detail_includes_sanitized_tool_traces_and_delete_receipt(self):
        detail = get_admin_conversation(self.db, self.conversation.id)
        self.assertEqual(detail.messages[0].tool_calls[0].tool_name, "get_scenic_summary")
        self.assertEqual(detail.messages[0].tool_calls[0].result_summary_json, {"result_count": 1})
        serialized = AdminAiConversationOut.model_validate(detail)
        self.assertEqual(serialized.messages[0].tool_calls[0].arguments_json, {
            "scenic_ids": ["zunyi-zoo"]
        })

        receipt = delete_admin_conversation(
            self.db, self.conversation.id, actor_id=1, reason="信息维护员手工删除"
        )

        self.assertEqual(receipt.mode, "admin")
        self.assertEqual(receipt.deleted_message_count, 1)
        self.assertEqual(receipt.actor_id, 1)
        self.assertIsNone(self.db.get(AiConversation, self.conversation.id))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AiMessage)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AiToolCall)), 0)

    def test_admin_keyword_searches_message_content(self):
        rows, total = list_admin_conversations(
            self.db,
            keyword="关键字",
            page=1,
            size=20,
        )
        self.assertEqual(total, 1)
        self.assertEqual([row.id for row in rows], [self.conversation.id])

    def test_four_admin_routes_are_registered_without_export(self):
        paths = {
            (method, route.path)
            for route in router.routes
            for method in route.methods
        }
        self.assertIn(("GET", "/admin/conversations"), paths)
        self.assertIn(("GET", "/admin/conversations/{conversation_id}"), paths)
        self.assertIn(("DELETE", "/admin/conversations/{conversation_id}"), paths)
        self.assertIn(("GET", "/admin/deletion-audits"), paths)
        self.assertFalse(any("export" in path for _, path in paths))

    @patch("app.jobs.cleanup_ai_conversations.cleanup_expired_conversations")
    @patch("app.jobs.cleanup_ai_conversations.preview_expired_conversations")
    @patch("app.jobs.cleanup_ai_conversations.SessionLocal")
    def test_cleanup_dry_run_reports_without_deleting(
        self, session_factory, preview, cleanup
    ):
        preview.return_value = CleanupResult(2, 5)

        result = run_cleanup(dry_run=True)

        self.assertEqual(result, 0)
        cleanup.assert_not_called()
        session_factory.return_value.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
