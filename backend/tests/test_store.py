import shutil
import socket
import subprocess
import time
import unittest
from unittest.mock import Mock, patch

from app.core.store import _MemoryStore, _RedisStore, _member_expiry_key


class _RedisCliClient:
    def __init__(self, executable: str, port: int) -> None:
        self._executable = executable
        self._port = port

    def execute(self, *args):
        completed = subprocess.run(
            [
                self._executable,
                "--raw",
                "-h",
                "127.0.0.1",
                "-p",
                str(self._port),
                *(str(arg) for arg in args),
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        output = (completed.stdout or completed.stderr).strip()
        if completed.returncode or output.startswith(("ERR ", "WRONGTYPE ")):
            raise RuntimeError(output or f"redis-cli exited {completed.returncode}")
        if output.lstrip("-").isdigit():
            return int(output)
        return output

    def eval(self, script, key_count, *args):
        return self.execute("EVAL", script, key_count, *args)

    def zrem(self, key, member):
        return self.execute("ZREM", key, member)


class _RedisIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server = shutil.which("redis-server")
        cli = shutil.which("redis-cli")
        if not server or not cli:
            raise unittest.SkipTest("redis-server and redis-cli are required")

        with socket.socket() as port_probe:
            port_probe.bind(("127.0.0.1", 0))
            port = port_probe.getsockname()[1]

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cls._process = subprocess.Popen(
            [
                server,
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        cls.redis = _RedisCliClient(cli, port)
        for _ in range(50):
            try:
                if cls.redis.execute("PING") == "PONG":
                    break
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass
            time.sleep(0.05)
        else:
            cls._process.terminate()
            cls._process.wait(timeout=5)
            raise unittest.SkipTest("ephemeral redis-server did not start")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.redis.execute("SHUTDOWN", "NOSAVE")
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            pass
        try:
            cls._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls._process.terminate()
            cls._process.wait(timeout=5)

    def setUp(self):
        self.redis.execute("FLUSHDB")


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
        (
            admission_script,
            key_count,
            key,
            expiry_key,
            member,
            limit,
            ttl,
        ) = client.eval.call_args.args
        self.assertIn("redis.call('TIME')", admission_script)
        self.assertIn("redis.call('TYPE', KEYS[1]).ok", admission_script)
        self.assertIn("redis.call('SCARD', KEYS[1])", admission_script)
        self.assertIn("redis.call('ZADD', KEYS[2], expires_at, ARGV[1])", admission_script)
        self.assertEqual(
            (key_count, key, expiry_key, member, limit, ttl),
            (2, "active", "active:expiries:v2", "request-a", 2, 30),
        )

        self.assertTrue(redis_store.renew_member("active", "request-a", ttl=30))
        renewal_script, key_count, key, expiry_key, member, ttl = client.eval.call_args.args
        prune = renewal_script.index("ZREMRANGEBYSCORE")
        ownership_check = renewal_script.index("if not redis.call('ZSCORE', KEYS[2]")
        renewal = renewal_script.index("redis.call('ZADD', KEYS[2]")
        self.assertLess(prune, ownership_check)
        self.assertLess(ownership_check, renewal)
        self.assertIn("then return 0 end", renewal_script)
        self.assertEqual(
            (key_count, key, expiry_key, member, ttl),
            (2, "active", "active:expiries:v2", "request-a", 30),
        )

        self.assertTrue(redis_store.remove_member("active", "request-a"))
        removal_script, key_count, key, expiry_key, member = client.eval.call_args.args
        self.assertIn("redis.call('SREM', KEYS[1], ARGV[1])", removal_script)
        self.assertIn("redis.call('ZREM', KEYS[2], ARGV[1])", removal_script)
        self.assertEqual(
            (key_count, key, expiry_key, member),
            (2, "active", "active:expiries:v2", "request-a"),
        )


class RedisMemberCompatibilityTest(_RedisIntegrationTest):
    _LEGACY_ADMISSION_SCRIPT = """
    if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1 then
        if tonumber(ARGV[3]) > 0 then redis.call('EXPIRE', KEYS[1], ARGV[3]) end
        return 1
    end
    if redis.call('SCARD', KEYS[1]) >= tonumber(ARGV[2]) then return 0 end
    redis.call('SADD', KEYS[1], ARGV[1])
    if tonumber(ARGV[3]) > 0 then redis.call('EXPIRE', KEYS[1], ARGV[3]) end
    return 1
    """

    def test_legacy_set_and_versioned_members_share_a_conservative_limit(self):
        key = "ai:user:7:active"
        self.redis.execute("SADD", key, "legacy-request")
        self.redis.execute("EXPIRE", key, 30)
        redis_store = _RedisStore(self.redis)

        self.assertTrue(redis_store.set_members(key, "new-request", limit=2, ttl=30))
        self.assertEqual(self.redis.execute("TYPE", key), "set")
        self.assertEqual(
            self.redis.execute("TYPE", _member_expiry_key(key)),
            "zset",
        )
        self.assertEqual(
            self.redis.eval(
                self._LEGACY_ADMISSION_SCRIPT,
                1,
                key,
                "second-legacy-request",
                2,
                30,
            ),
            0,
        )

        self.assertTrue(redis_store.remove_member(key, "new-request"))
        self.assertEqual(
            self.redis.eval(
                self._LEGACY_ADMISSION_SCRIPT,
                1,
                key,
                "second-legacy-request",
                2,
                30,
            ),
            1,
        )

        new_first_key = "ai:user:8:active"
        self.assertTrue(
            redis_store.set_members(new_first_key, "new-first", limit=2, ttl=30)
        )
        self.assertEqual(self.redis.execute("TYPE", new_first_key), "set")
        self.assertEqual(
            self.redis.eval(
                self._LEGACY_ADMISSION_SCRIPT,
                1,
                new_first_key,
                "legacy-second",
                2,
                30,
            ),
            1,
        )
        self.assertFalse(
            redis_store.set_members(new_first_key, "blocked-third", limit=2, ttl=30)
        )

    def test_versioned_expiry_prunes_only_the_expired_member_from_legacy_set(self):
        key = "ai:user:7:active"
        redis_store = _RedisStore(self.redis)
        self.assertTrue(redis_store.set_members(key, "request-a", limit=2, ttl=30))
        self.assertTrue(redis_store.set_members(key, "request-b", limit=2, ttl=30))

        self.redis.execute("ZADD", _member_expiry_key(key), 0, "request-a")

        self.assertTrue(redis_store.renew_member(key, "request-b", ttl=30))
        self.assertTrue(redis_store.set_members(key, "request-c", limit=2, ttl=30))
        self.assertFalse(redis_store.set_members(key, "request-d", limit=2, ttl=30))
        self.assertEqual(
            set(self.redis.execute("SMEMBERS", key).splitlines()),
            {"request-b", "request-c"},
        )

    def test_legacy_member_ages_out_while_a_v2_member_keeps_renewing(self):
        key = "ai:user:9:active"
        redis_store = _RedisStore(self.redis)
        self.redis.execute("SADD", key, "legacy-crashed")
        self.redis.execute("EXPIRE", key, 30)
        self.assertTrue(redis_store.set_members(key, "v2-active", limit=2, ttl=30))

        # Simulate the bounded legacy expiry passing while the v2 request renews.
        self.redis.execute("ZADD", _member_expiry_key(key), 0, "legacy-crashed")
        self.assertTrue(redis_store.renew_member(key, "v2-active", ttl=30))
        self.assertTrue(redis_store.renew_member(key, "v2-active", ttl=30))
        self.assertEqual(set(self.redis.execute("SMEMBERS", key).splitlines()), {"v2-active"})

    def test_full_legacy_set_is_migrated_before_v2_capacity_rejection(self):
        key = "ai:user:10:active"
        redis_store = _RedisStore(self.redis)
        self.redis.execute("SADD", key, "legacy-crashed")
        self.redis.execute("EXPIRE", key, 30)

        self.assertFalse(redis_store.set_members(key, "v2-blocked", limit=1, ttl=30))
        self.assertIsNotNone(self.redis.execute("ZSCORE", _member_expiry_key(key), "legacy-crashed"))

    def test_existing_round_three_sorted_set_is_handled_without_wrongtype(self):
        key = "ai:user:7:active"
        self.redis.execute("ZADD", key, 9999999999, "round-three-request")
        self.redis.execute("EXPIRE", key, 30)
        redis_store = _RedisStore(self.redis)

        self.assertTrue(redis_store.set_members(key, "new-request", limit=2, ttl=30))
        self.assertFalse(redis_store.set_members(key, "blocked-request", limit=2, ttl=30))
        self.assertTrue(redis_store.renew_member(key, "new-request", ttl=30))
        self.assertTrue(redis_store.remove_member(key, "new-request"))
        self.assertEqual(self.redis.execute("TYPE", key), "zset")


if __name__ == "__main__":
    unittest.main()
