import unittest
import time
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
from app.services import ai_runtime
from app.services.ai_conversations import (
    CleanupResult,
    cleanup_expired_conversations,
    delete_admin_conversation,
    delete_owned_conversation,
    get_admin_conversation,
    get_owned_conversation,
    list_admin_conversations,
    preview_expired_conversations,
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
    def setUp(self):
        ai_runtime.reset_for_tests()

    def tearDown(self):
        ai_runtime.reset_for_tests()

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

    def test_retention_skips_active_conversations_and_counts_deleted_rows(self):
        now = datetime(2026, 8, 5, 1, 0)
        active_row = SimpleNamespace(id=5, owner_id=2, last_active_at=now - timedelta(days=91), messages=[1, 2])
        expired_row = SimpleNamespace(id=6, owner_id=3, last_active_at=now - timedelta(days=91), messages=[3])
        db = Mock()
        db.scalars.return_value.all.return_value = [active_row, expired_row]
        lease = ai_runtime.acquire_generation(2, active_row.id, "active-retention")

        try:
            result = cleanup_expired_conversations(db, now=now)
        finally:
            ai_runtime.release_generation(lease)

        self.assertEqual(result, CleanupResult(deleted_conversations=1, deleted_messages=1))
        self.assertEqual(db.add.call_args.args[0].conversation_id, 6)
        self.assertEqual(db.delete.call_args.args[0], expired_row)

    @patch("app.services.ai_conversations.ai_runtime.try_acquire_deletion_reservation")
    def test_retention_skips_when_generation_wins_after_selection(self, reserve):
        now = datetime(2026, 8, 5, 1, 0)
        row = SimpleNamespace(
            id=8,
            owner_id=2,
            last_active_at=now - timedelta(days=91),
            messages=[1],
        )
        db = Mock()
        db.scalars.return_value.all.return_value = [row]
        leases = []

        def generation_wins(conversation_id):
            leases.append(ai_runtime.acquire_generation(2, conversation_id, "late-generation"))
            return None

        reserve.side_effect = generation_wins
        try:
            result = cleanup_expired_conversations(db, now=now)
        finally:
            for lease in leases:
                ai_runtime.release_generation(lease)

        self.assertEqual(result, CleanupResult(0, 0))
        db.delete.assert_not_called()
        db.add.assert_not_called()
        db.commit.assert_not_called()

    @patch("app.services.ai_conversations.ai_runtime.release_deletion_reservation")
    def test_retention_holds_reservation_through_commit(self, release):
        now = datetime(2026, 8, 5, 1, 0)
        row = SimpleNamespace(
            id=9,
            owner_id=2,
            last_active_at=now - timedelta(days=91),
            messages=[1],
        )
        db = Mock()
        db.scalars.return_value.all.return_value = [row]
        db.commit.side_effect = lambda: self.assertFalse(release.called)

        result = cleanup_expired_conversations(db, now=now)

        self.assertEqual(result, CleanupResult(1, 1))
        release.assert_called_once()

    def test_retention_rolls_back_if_reservation_expires_to_successor(self):
        now_value = datetime(2026, 8, 5, 1, 0)
        row = SimpleNamespace(
            id=12,
            owner_id=2,
            last_active_at=now_value - timedelta(days=91),
            messages=[1],
        )
        db = Mock()
        db.scalars.return_value.all.return_value = [row]
        successors = []

        def start_without_thread(heartbeat):
            heartbeat.assert_owned()

        with (
            patch.object(ai_runtime.settings, "AI_GENERATION_LEASE_SECONDS", 1),
            patch.object(
                ai_runtime.DeletionReservationHeartbeat,
                "start",
                start_without_thread,
            ),
            patch("app.core.store.time.time") as clock,
        ):
            clock.return_value = 100.0

            def generation_wins_before_commit(_conversation):
                clock.return_value = 102.0
                successors.append(ai_runtime.acquire_generation(
                    2, row.id, "retention-successor"
                ))

            db.delete.side_effect = generation_wins_before_commit
            result = cleanup_expired_conversations(db, now=now_value)
            self.assertEqual(
                ai_runtime.runtime_store.get(f"ai:conversation:{row.id}:lease"),
                "retention-successor",
            )
            for lease in successors:
                ai_runtime.release_generation(lease)

        self.assertEqual(result, CleanupResult(0, 0))
        db.commit.assert_not_called()
        db.rollback.assert_called_once_with()

    @patch("app.services.ai_conversations.ai_runtime.release_deletion_reservation")
    @patch("app.services.ai_conversations.ai_runtime.renew_deletion_reservation", return_value=True)
    @patch("app.services.ai_conversations.ai_runtime.try_acquire_deletion_reservation")
    def test_retention_scans_past_all_active_first_500(self, reserve, renew, release):
        now = datetime(2026, 8, 5, 1, 0)
        stale_at = now - timedelta(days=91)
        active_rows = [
            SimpleNamespace(id=index, owner_id=2, last_active_at=stale_at, messages=[index])
            for index in range(1, 501)
        ]
        deletable = SimpleNamespace(
            id=501, owner_id=3, last_active_at=stale_at, messages=[1, 2]
        )
        db = Mock()
        db.scalars.side_effect = [
            SimpleNamespace(all=lambda: active_rows),
            SimpleNamespace(all=lambda: [deletable]),
        ]
        reservation = ai_runtime.DeletionReservation(501, "deletion:test-501")
        reserve.side_effect = lambda conversation_id: (
            reservation if conversation_id == 501 else None
        )

        result = cleanup_expired_conversations(db, now=now)

        self.assertEqual(result, CleanupResult(1, 2))
        self.assertEqual(db.scalars.call_count, 2)
        db.delete.assert_called_once_with(deletable)
        release.assert_called_once_with(reservation)

    @patch("app.services.ai_conversations.ai_runtime.is_conversation_occupied")
    def test_preview_scans_past_active_prefix_without_reserving(self, occupied):
        now = datetime(2026, 8, 5, 1, 0)
        stale_at = now - timedelta(days=91)
        active_rows = [
            SimpleNamespace(id=index, owner_id=2, last_active_at=stale_at, messages=[index])
            for index in range(1, 501)
        ]
        deletable = SimpleNamespace(
            id=501, owner_id=3, last_active_at=stale_at, messages=[1, 2, 3]
        )
        db = Mock()
        db.scalars.side_effect = [
            SimpleNamespace(all=lambda: active_rows),
            SimpleNamespace(all=lambda: [deletable]),
        ]
        occupied.side_effect = lambda conversation_id: conversation_id <= 500

        result = preview_expired_conversations(db, now=now)

        self.assertEqual(result, CleanupResult(1, 3))
        self.assertEqual(db.scalars.call_count, 2)

    @patch("app.services.ai_conversations.ai_runtime.try_acquire_deletion_reservation", return_value=None)
    @patch("app.services.ai_conversations.ai_runtime.is_conversation_occupied", return_value=True)
    def test_preview_and_cleanup_terminate_after_all_busy_pages(self, occupied, reserve):
        now = datetime(2026, 8, 5, 1, 0)
        stale_at = now - timedelta(days=91)
        active_rows = [
            SimpleNamespace(id=index, owner_id=2, last_active_at=stale_at, messages=[])
            for index in range(1, 501)
        ]
        preview_db = Mock()
        preview_db.scalars.side_effect = [
            SimpleNamespace(all=lambda: active_rows),
            SimpleNamespace(all=lambda: []),
        ]
        cleanup_db = Mock()
        cleanup_db.scalars.side_effect = [
            SimpleNamespace(all=lambda: active_rows),
            SimpleNamespace(all=lambda: []),
        ]

        preview = preview_expired_conversations(preview_db, now=now)
        cleanup = cleanup_expired_conversations(cleanup_db, now=now)

        self.assertEqual(preview, CleanupResult(0, 0))
        self.assertEqual(cleanup, CleanupResult(0, 0))
        self.assertEqual(preview_db.scalars.call_count, 2)
        self.assertEqual(cleanup_db.scalars.call_count, 2)


class AiAdminConversationTest(unittest.TestCase):
    def setUp(self):
        ai_runtime.reset_for_tests()
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
        ai_runtime.reset_for_tests()

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

    @patch("app.services.ai_conversations._GENERATION_STOP_WAIT_SECONDS", 0)
    @patch("app.services.ai_conversations.ai_runtime.try_acquire_deletion_reservation", return_value=None)
    @patch("app.services.ai_conversations.ai_runtime.request_stop")
    def test_admin_delete_does_not_delete_active_generation(self, request_stop, reserve):
        generating = AiMessage(
            conversation_id=self.conversation.id,
            role="assistant",
            content="",
            status="generating",
            request_id="request-generating",
            actions_json=[],
        )
        self.db.add(generating)
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            delete_admin_conversation(self.db, self.conversation.id, actor_id=1, reason="reason")

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "conversation_busy")
        request_stop.assert_called_once_with(generating.id)
        self.assertIsNotNone(self.db.get(AiConversation, self.conversation.id))

    @patch("app.services.ai_conversations.ai_runtime.release_deletion_reservation")
    @patch("app.services.ai_conversations.ai_runtime.renew_deletion_reservation", return_value=True)
    @patch("app.services.ai_conversations.ai_runtime.try_acquire_deletion_reservation")
    @patch("app.services.ai_conversations.ai_runtime.request_stop")
    @patch("app.services.ai_conversations.time.sleep")
    def test_owner_delete_waits_for_cleared_generation_then_deletes(
        self, sleep, request_stop, reserve, renew, release
    ):
        generating = AiMessage(
            conversation_id=self.conversation.id,
            role="assistant",
            content="",
            status="generating",
            request_id="request-generating-owner",
            actions_json=[],
        )
        self.db.add(generating)
        self.db.commit()
        reservation = ai_runtime.DeletionReservation(
            self.conversation.id, "deletion:owner-cleared"
        )
        reserve.side_effect = [None, reservation]

        receipt = delete_owned_conversation(self.db, self.conversation.id, user_id=7)

        self.assertEqual(receipt.deleted_message_count, 2)
        request_stop.assert_called_once_with(generating.id)
        self.assertIsNone(self.db.get(AiConversation, self.conversation.id))
        release.assert_called_once_with(reservation)

    @patch("app.services.ai_conversations._GENERATION_STOP_WAIT_SECONDS", 0)
    @patch("app.services.ai_conversations.ai_runtime.request_stop")
    def test_active_lease_without_generating_message_is_not_deleted(
        self, request_stop
    ):
        lease = ai_runtime.acquire_generation(7, self.conversation.id, "generation-wins")
        try:
            with self.assertRaises(HTTPException) as raised:
                delete_owned_conversation(self.db, self.conversation.id, user_id=7)
        finally:
            ai_runtime.release_generation(lease)

        self.assertEqual(raised.exception.detail["code"], "conversation_busy")
        request_stop.assert_not_called()
        self.assertIsNotNone(self.db.get(AiConversation, self.conversation.id))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AiDeletionAudit)), 0)

    @patch("app.services.ai_conversations.time.monotonic", side_effect=[0, 0, 1])
    @patch("app.services.ai_conversations.time.sleep")
    def test_generation_reacquisition_wins_before_deletion_reservation(
        self, sleep, monotonic
    ):
        first = ai_runtime.acquire_generation(7, self.conversation.id, "first-generation")
        current = []

        def reacquire(_seconds):
            ai_runtime.release_generation(first)
            current.append(ai_runtime.acquire_generation(
                7, self.conversation.id, "reacquired-generation"
            ))

        sleep.side_effect = reacquire
        try:
            with self.assertRaises(HTTPException) as raised:
                delete_owned_conversation(self.db, self.conversation.id, user_id=7)
        finally:
            ai_runtime.release_generation(first)
            for lease in current:
                ai_runtime.release_generation(lease)

        self.assertEqual(raised.exception.detail["code"], "conversation_busy")
        self.assertIsNotNone(self.db.get(AiConversation, self.conversation.id))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AiDeletionAudit)), 0)

    @patch("app.services.ai_conversations.ai_runtime.request_stop")
    def test_stale_generating_message_is_stopped_and_deleted_under_reservation(
        self, request_stop
    ):
        stale = AiMessage(
            conversation_id=self.conversation.id,
            role="assistant",
            content="",
            status="generating",
            request_id="stale-generating",
            actions_json=[],
        )
        self.db.add(stale)
        self.db.commit()

        receipt = delete_owned_conversation(self.db, self.conversation.id, user_id=7)

        self.assertEqual(receipt.deleted_message_count, 2)
        request_stop.assert_called_once_with(stale.id)
        self.assertIsNone(self.db.get(AiConversation, self.conversation.id))

    @patch.object(ai_runtime.settings, "AI_GENERATION_LEASE_SECONDS", 1)
    def test_deletion_heartbeat_survives_commit_longer_than_original_ttl(self):
        original_commit = self.db.commit
        blocked_attempts = []

        def blocked_commit():
            time.sleep(1.1)
            try:
                ai_runtime.acquire_generation(
                    7, self.conversation.id, "during-blocked-commit"
                )
            except HTTPException as exc:
                blocked_attempts.append(exc)
            original_commit()

        with patch.object(self.db, "commit", side_effect=blocked_commit):
            receipt = delete_owned_conversation(
                self.db, self.conversation.id, user_id=7
            )

        self.assertEqual(receipt.deleted_message_count, 1)
        self.assertEqual(len(blocked_attempts), 1)
        self.assertEqual(blocked_attempts[0].detail["code"], "conversation_busy")

    def test_owner_delete_rolls_back_after_reservation_successor_wins(self):
        successors = []

        def start_without_thread(heartbeat):
            heartbeat.assert_owned()

        with (
            patch.object(ai_runtime.settings, "AI_GENERATION_LEASE_SECONDS", 1),
            patch.object(
                ai_runtime.DeletionReservationHeartbeat,
                "start",
                start_without_thread,
            ),
            patch(
                "app.services.ai_conversations._reload_messages_under_reservation"
            ) as reload_messages,
            patch("app.core.store.time.time") as clock,
        ):
            clock.return_value = 100.0

            def expire_then_reacquire(_db, conversation):
                clock.return_value = 102.0
                successors.append(ai_runtime.acquire_generation(
                    7, conversation.id, "owner-successor"
                ))
                return list(conversation.messages)

            reload_messages.side_effect = expire_then_reacquire
            with self.assertRaises(HTTPException) as raised:
                delete_owned_conversation(self.db, self.conversation.id, user_id=7)
            self.assertEqual(
                ai_runtime.runtime_store.get(
                    f"ai:conversation:{self.conversation.id}:lease"
                ),
                "owner-successor",
            )
            for lease in successors:
                ai_runtime.release_generation(lease)

        self.assertEqual(raised.exception.detail["code"], "conversation_busy")
        self.assertIsNotNone(self.db.get(AiConversation, self.conversation.id))

    @patch("app.services.ai_conversations.ai_runtime.release_deletion_reservation")
    @patch("app.services.ai_conversations.ai_runtime.renew_deletion_reservation", return_value=True)
    @patch("app.services.ai_conversations.ai_runtime.try_acquire_deletion_reservation")
    def test_delete_reloads_messages_after_reservation(self, reserve, renew, release):
        reservation = ai_runtime.DeletionReservation(
            self.conversation.id, "deletion:reload-test"
        )

        def persist_late_message(_conversation_id):
            self.db.add(AiMessage(
                conversation_id=self.conversation.id,
                role="assistant",
                content="late completion",
                status="completed",
                request_id="late-completion",
                actions_json=[],
            ))
            self.db.commit()
            return reservation

        reserve.side_effect = persist_late_message

        receipt = delete_owned_conversation(self.db, self.conversation.id, user_id=7)

        self.assertEqual(receipt.deleted_message_count, 2)
        release.assert_called_once_with(reservation)

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
