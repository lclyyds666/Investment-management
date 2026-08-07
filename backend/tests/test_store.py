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


if __name__ == "__main__":
    unittest.main()
