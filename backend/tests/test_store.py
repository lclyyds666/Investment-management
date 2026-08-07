import unittest
from unittest.mock import Mock, patch

from app.core.store import _MemoryStore, _RedisStore


class CompareExpireStoreTest(unittest.TestCase):
    def test_memory_compare_expire_renews_only_the_owned_value(self):
        memory = _MemoryStore()
        with patch("app.core.store.time.time", return_value=100.0):
            memory.set("lease", "owner-a", ttl=1)

        with patch("app.core.store.time.time", return_value=100.75):
            self.assertFalse(memory.compare_expire("lease", "owner-b", ttl=1))
            self.assertTrue(memory.compare_expire("lease", "owner-a", ttl=1))

        with patch("app.core.store.time.time", return_value=101.5):
            self.assertEqual(memory.get("lease"), "owner-a")
        with patch("app.core.store.time.time", return_value=102.0):
            self.assertIsNone(memory.get("lease"))

    def test_redis_compare_expire_uses_atomic_compare_and_expire_script(self):
        client = Mock()
        client.eval.return_value = 1
        redis_store = _RedisStore(client)

        self.assertTrue(redis_store.compare_expire("lease", "owner-a", ttl=30))

        script, key_count, key, owner, ttl = client.eval.call_args.args
        self.assertIn("redis.call('GET', KEYS[1]) == ARGV[1]", script)
        self.assertIn("redis.call('EXPIRE', KEYS[1], ARGV[2])", script)
        self.assertEqual((key_count, key, owner, ttl), (1, "lease", "owner-a", 30))


class MemberExpiryStoreTest(unittest.TestCase):
    def test_memory_renewal_does_not_keep_other_members_alive(self):
        memory = _MemoryStore()
        with patch("app.core.store.time.time") as now:
            now.return_value = 100.0
            self.assertTrue(memory.set_members("active", "request-a", limit=2, ttl=1))
            self.assertTrue(memory.set_members("active", "request-b", limit=2, ttl=1))

            now.return_value = 100.75
            self.assertTrue(memory.renew_member("active", "request-b", ttl=1))

            now.return_value = 101.25
            self.assertFalse(memory.renew_member("active", "request-a", ttl=1))
            self.assertTrue(memory.set_members("active", "request-c", limit=2, ttl=1))
            self.assertFalse(memory.set_members("active", "request-d", limit=2, ttl=1))

    def test_redis_member_scripts_prune_expired_scores_and_renew_only_owned_members(self):
        client = Mock()
        client.eval.return_value = 1
        redis_store = _RedisStore(client)

        self.assertTrue(redis_store.set_members("active", "request-a", limit=2, ttl=30))
        admission_script, key_count, key, member, limit, ttl = client.eval.call_args.args
        self.assertIn("redis.call('TIME')", admission_script)
        self.assertIn("redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)", admission_script)
        self.assertIn("redis.call('ZCARD', KEYS[1])", admission_script)
        self.assertIn("redis.call('ZADD', KEYS[1], expires_at, ARGV[1])", admission_script)
        self.assertEqual(
            (key_count, key, member, limit, ttl),
            (1, "active", "request-a", 2, 30),
        )

        self.assertTrue(redis_store.renew_member("active", "request-a", ttl=30))
        renewal_script, key_count, key, member, ttl = client.eval.call_args.args
        prune = renewal_script.index("ZREMRANGEBYSCORE")
        ownership_check = renewal_script.index("if not redis.call('ZSCORE'")
        renewal = renewal_script.index("redis.call('ZADD'")
        self.assertLess(prune, ownership_check)
        self.assertLess(ownership_check, renewal)
        self.assertIn("then return 0 end", renewal_script)
        self.assertEqual(
            (key_count, key, member, ttl),
            (1, "active", "request-a", 30),
        )

        self.assertTrue(redis_store.remove_member("active", "request-a"))
        client.zrem.assert_called_once_with("active", "request-a")


if __name__ == "__main__":
    unittest.main()
