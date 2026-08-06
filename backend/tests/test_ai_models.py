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
        foreign_keys = {
            foreign_key.target_fullname
            for foreign_key in AiDeletionAudit.__table__.foreign_keys
        }
        self.assertNotIn("ai_conversation.id", foreign_keys)
        self.assertNotIn("content", AiDeletionAudit.__table__.columns)

    def test_conversation_has_retention_and_activity_fields(self):
        columns = set(AiConversation.__table__.columns.keys())
        self.assertTrue({"owner_id", "last_active_at", "expires_at"}.issubset(columns))

    def test_conversation_and_message_content_cascade(self):
        conversation_fk = next(iter(AiMessage.__table__.c.conversation_id.foreign_keys))
        self.assertEqual(conversation_fk.ondelete, "CASCADE")


if __name__ == "__main__":
    unittest.main()
