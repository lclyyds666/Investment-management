"""带 TTL 的键值存储抽象层（图形验证码 / 登录防爆破计数用）。

设计遵循本项目一贯的「优雅降级」哲学（对齐 AI 智能体无 Key 回退规则引擎）：
- 配置了 ``REDIS_URL`` 且 redis 库可用、连接可 ping 通  → 使用 Redis 后端（生产、多进程共享）；
- 否则（未装 redis / 未配置 / 连接失败）        → 自动回退到进程内存后端。

对上层而言接口完全一致，缺少 Redis 基础设施也不会让接口报错，仅退化为单进程内有效。
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.core.config import settings


def _member_expiry_key(key: str) -> str:
    return f"{key}:expiries:v2"


class _MemoryStore:
    """进程内存实现：dict[key] = (value, expire_ts)。线程安全、惰性过期。"""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}
        self._sets: dict[str, dict[str, float]] = {}
        self._lock = threading.Lock()

    def _alive(self, key: str) -> Optional[tuple[str, float]]:
        item = self._data.get(key)
        if item is None:
            return None
        _, expire = item
        if expire and expire < time.time():
            self._data.pop(key, None)
            return None
        return item

    def _alive_set(self, key: str) -> Optional[dict[str, float]]:
        members = self._sets.get(key)
        if members is None:
            return None
        now = time.time()
        for member in [
            member
            for member, expire in members.items()
            if expire and expire < now
        ]:
            members.pop(member, None)
        if not members:
            self._sets.pop(key, None)
            return None
        return members

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            item = self._alive(key)
            return item[0] if item else None

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (str(value), time.time() + ttl if ttl else 0)

    def set_if_absent(self, key: str, value: str, ttl: int) -> bool:
        with self._lock:
            if self._alive(key) is not None:
                return False
            self._data[key] = (str(value), time.time() + ttl if ttl else 0)
            return True

    def compare_delete(self, key: str, expected: str) -> bool:
        with self._lock:
            item = self._alive(key)
            if item is None or item[0] != str(expected):
                return False
            self._data.pop(key, None)
            return True

    def compare_expire(self, key: str, expected: str, ttl: int) -> bool:
        with self._lock:
            item = self._alive(key)
            if item is None or item[0] != str(expected):
                return False
            self._data[key] = (
                item[0],
                time.time() + ttl if ttl else 0,
            )
            return True

    def set_members(self, key: str, member: str, limit: int, ttl: int) -> bool:
        with self._lock:
            members = self._alive_set(key) or {}
            member = str(member)
            if member in members:
                members[member] = time.time() + ttl if ttl else 0
                self._sets[key] = members
                return True
            if len(members) >= limit:
                return False
            members[member] = time.time() + ttl if ttl else 0
            self._sets[key] = members
            return True

    def renew_member(self, key: str, member: str, ttl: int) -> bool:
        with self._lock:
            members = self._alive_set(key)
            member = str(member)
            if members is None or member not in members:
                return False
            members[member] = time.time() + ttl if ttl else 0
            return True

    def remove_member(self, key: str, member: str) -> bool:
        with self._lock:
            members = self._alive_set(key)
            if members is None or str(member) not in members:
                return False
            members.pop(str(member), None)
            if not members:
                self._sets.pop(key, None)
            return True

    def incr(self, key: str, ttl: int) -> int:
        with self._lock:
            item = self._alive(key)
            cur = int(item[0]) + 1 if item else 1
            # 首次创建时设置 TTL；已存在则沿用原到期时间（滑动窗口由业务决定）
            expire = item[1] if item else (time.time() + ttl if ttl else 0)
            self._data[key] = (str(cur), expire)
            return cur

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
            self._sets.pop(key, None)

    def clear_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in [key for key in self._data if key.startswith(prefix)]:
                self._data.pop(key, None)
            for key in [key for key in self._sets if key.startswith(prefix)]:
                self._sets.pop(key, None)

    def ttl(self, key: str) -> int:
        with self._lock:
            item = self._alive(key)
            if not item or not item[1]:
                return -1
            return max(0, int(item[1] - time.time()))


class _RedisStore:
    """Redis 后端封装。所有值以字符串存储。"""

    def __init__(self, client) -> None:
        self._r = client

    def get(self, key: str) -> Optional[str]:
        return self._r.get(key)

    def set(self, key: str, value: str, ttl: int) -> None:
        self._r.set(key, str(value), ex=ttl if ttl else None)

    def set_if_absent(self, key: str, value: str, ttl: int) -> bool:
        return bool(self._r.set(key, str(value), ex=ttl if ttl else None, nx=True))

    def compare_delete(self, key: str, expected: str) -> bool:
        script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        end
        return 0
        """
        return bool(self._r.eval(script, 1, key, str(expected)))

    def compare_expire(self, key: str, expected: str, ttl: int) -> bool:
        script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('EXPIRE', KEYS[1], ARGV[2])
        end
        return 0
        """
        return bool(self._r.eval(script, 1, key, str(expected), int(ttl)))

    def set_members(self, key: str, member: str, limit: int, ttl: int) -> bool:
        script = """
        local expiry_type = redis.call('TYPE', KEYS[2]).ok
        local legacy_type = redis.call('TYPE', KEYS[1]).ok
        if expiry_type ~= 'none' and expiry_type ~= 'zset' then return 0 end
        if legacy_type ~= 'none' and legacy_type ~= 'set' and legacy_type ~= 'zset' then
            return 0
        end

        local clock = redis.call('TIME')
        local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
        local ttl = tonumber(ARGV[3])
        local expires_at = ttl > 0 and now + ttl or 9007199254740991

        if expiry_type == 'zset' then
            if legacy_type == 'set' then
                local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', now)
                if #expired > 0 then
                    redis.call('SREM', KEYS[1], unpack(expired))
                    redis.call('ZREM', KEYS[2], unpack(expired))
                end
            else
                redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
                if legacy_type == 'zset' then
                    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
                end
            end
        end

        local legacy_missing = legacy_type == 'none'
        if legacy_type == 'none' then legacy_type = 'set' end
        if legacy_type == 'set' then
            -- Stamp legacy members before the capacity check, including a full
            -- Set, so migration cannot be blocked by an unbounded v1 member.
            local legacy_members = redis.call('SMEMBERS', KEYS[1])
            for _, legacy_member in ipairs(legacy_members) do
                local legacy_score = redis.call('ZSCORE', KEYS[2], legacy_member)
                if legacy_score == false then
                    redis.call('ZADD', KEYS[2], expires_at, legacy_member)
                end
            end
        end
        if expiry_type == 'zset' then
            local active = redis.call('ZRANGE', KEYS[2], 0, -1, 'WITHSCORES')
            for index = 1, #active, 2 do
                if legacy_type == 'set' then
                    redis.call('SADD', KEYS[1], active[index])
                else
                    redis.call('ZADD', KEYS[1], active[index + 1], active[index])
                end
            end
        end

        local present
        local count
        if legacy_type == 'set' then
            present = redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1
            count = redis.call('SCARD', KEYS[1])
        else
            present = redis.call('ZSCORE', KEYS[1], ARGV[1]) ~= false
            count = redis.call('ZCARD', KEYS[1])
        end
        if not present and count >= tonumber(ARGV[2]) then return 0 end

        redis.call('ZADD', KEYS[2], expires_at, ARGV[1])
        if legacy_type == 'set' then
            redis.call('SADD', KEYS[1], ARGV[1])
        else
            redis.call('ZADD', KEYS[1], expires_at, ARGV[1])
        end
        if ttl > 0 then
            -- Never renew an existing legacy Set: that would keep crashed v1
            -- members alive forever while a v2 request renews its own lease.
            if legacy_missing then redis.call('EXPIRE', KEYS[1], ttl) end
            redis.call('EXPIRE', KEYS[2], ttl)
        end
        return 1
        """
        return bool(
            self._r.eval(
                script,
                2,
                key,
                _member_expiry_key(key),
                str(member),
                int(limit),
                int(ttl),
            )
        )

    def renew_member(self, key: str, member: str, ttl: int) -> bool:
        script = """
        local expiry_type = redis.call('TYPE', KEYS[2]).ok
        local legacy_type = redis.call('TYPE', KEYS[1]).ok
        if expiry_type ~= 'zset' then return 0 end
        if legacy_type ~= 'none' and legacy_type ~= 'set' and legacy_type ~= 'zset' then
            return 0
        end

        local clock = redis.call('TIME')
        local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
        local ttl = tonumber(ARGV[2])
        local expires_at = ttl > 0 and now + ttl or 9007199254740991

        local legacy_missing = legacy_type == 'none'
        if legacy_type == 'set' then
            local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', now)
            if #expired > 0 then
                redis.call('SREM', KEYS[1], unpack(expired))
                redis.call('ZREM', KEYS[2], unpack(expired))
            end
        else
            redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
            if legacy_type == 'zset' then
                redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
            end
        end
        if not redis.call('ZSCORE', KEYS[2], ARGV[1]) then return 0 end

        redis.call('ZADD', KEYS[2], expires_at, ARGV[1])
        if legacy_type == 'set' then
            local legacy_members = redis.call('SMEMBERS', KEYS[1])
            for _, legacy_member in ipairs(legacy_members) do
                local legacy_score = redis.call('ZSCORE', KEYS[2], legacy_member)
                if legacy_score == false then
                    redis.call('ZADD', KEYS[2], expires_at, legacy_member)
                end
            end
        end
        if legacy_type == 'none' then legacy_type = 'set' end
        local active = redis.call('ZRANGE', KEYS[2], 0, -1, 'WITHSCORES')
        for index = 1, #active, 2 do
            if legacy_type == 'set' then
                redis.call('SADD', KEYS[1], active[index])
            else
                redis.call('ZADD', KEYS[1], active[index + 1], active[index])
            end
        end
        if ttl > 0 then
            if legacy_missing then redis.call('EXPIRE', KEYS[1], ttl) end
            redis.call('EXPIRE', KEYS[2], ttl)
        end
        return 1
        """
        return bool(
            self._r.eval(
                script,
                2,
                key,
                _member_expiry_key(key),
                str(member),
                int(ttl),
            )
        )

    def remove_member(self, key: str, member: str) -> bool:
        script = """
        local expiry_type = redis.call('TYPE', KEYS[2]).ok
        local legacy_type = redis.call('TYPE', KEYS[1]).ok
        if expiry_type ~= 'none' and expiry_type ~= 'zset' then return 0 end
        if legacy_type ~= 'none' and legacy_type ~= 'set' and legacy_type ~= 'zset' then
            return 0
        end

        local removed = 0
        if expiry_type == 'zset' then
            removed = redis.call('ZREM', KEYS[2], ARGV[1])
        end
        if legacy_type == 'set' then
            if redis.call('SREM', KEYS[1], ARGV[1]) == 1 then removed = 1 end
        elseif legacy_type == 'zset' then
            if redis.call('ZREM', KEYS[1], ARGV[1]) == 1 then removed = 1 end
        end
        return removed
        """
        return bool(
            self._r.eval(
                script,
                2,
                key,
                _member_expiry_key(key),
                str(member),
            )
        )

    def incr(self, key: str, ttl: int) -> int:
        script = """
        local current = redis.call('INCR', KEYS[1])
        if current == 1 and tonumber(ARGV[1]) > 0 then
            redis.call('EXPIRE', KEYS[1], ARGV[1])
        end
        return current
        """
        return int(self._r.eval(script, 1, key, int(ttl)))

    def delete(self, key: str) -> None:
        self._r.delete(key)

    def clear_prefix(self, prefix: str) -> None:
        keys = list(self._r.scan_iter(match=f"{prefix}*", count=100))
        if keys:
            self._r.delete(*keys)

    def ttl(self, key: str) -> int:
        return int(self._r.ttl(key))


def _build_store():
    """按配置构建后端；任何异常都回退内存实现，保证可用性。"""
    url = (settings.REDIS_URL or "").strip()
    if not url:
        return _MemoryStore()
    try:
        import redis  # 延迟导入：未安装 redis 库时不影响其余功能

        client = redis.from_url(url, decode_responses=True, socket_connect_timeout=1.5)
        client.ping()
        return _RedisStore(client)
    except Exception:  # noqa: BLE001 —— 连接失败即静默降级到内存实现
        return _MemoryStore()


# 全局单例。首次导入时按环境决定后端。
store = _build_store()


def backend_name() -> str:
    """返回当前后端名称（供健康检查 / 排障展示）。"""
    return "redis" if isinstance(store, _RedisStore) else "memory"


def validate_shared_store_requirement() -> None:
    if settings.AI_SHARED_STORE_REQUIRED and backend_name() != "redis":
        raise RuntimeError("AI shared storage requires a reachable Redis backend")


validate_shared_store_requirement()
