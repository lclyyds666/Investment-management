import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.api.v1.endpoints.health import health_check
from app.core import store
from app.services import ai_runtime


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


if __name__ == "__main__":
    unittest.main()
