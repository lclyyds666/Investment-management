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
            "这个平台是干什么的？",
            "介绍一下三个业务系统的建设情况。",
        ])

    @patch("app.services.ai_conversations.has_resource", return_value=True)
    def test_scenic_permission_adds_aggregate_prompts(self, allowed):
        questions = suggestions_for_user(Mock(), SimpleNamespace(is_superuser=False))
        self.assertIn("遵义动物园上个月经营数据。", questions)
        self.assertIn("对比遵义动物园和南阳森林野生动物世界今年经营数据。", questions)


if __name__ == "__main__":
    unittest.main()
