"""中间件 #1: Prompt Caching 模拟。

策略：
1. **剥离 cache_control 字段** — 避免上游报错。
2. **响应级缓存** — 对完全相同的请求直接返回缓存响应（适合 Claude Code 反复 dry-run）。
3. **前缀缓存** — 相同 (system + tools + messages[:-1]) 的请求记录 token 统计，注入 cache_read 占位。
4. SQLite 持久化，进程重启不丢。
"""
from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path
from typing import Any
import aiosqlite

from ..config import CacheCfg
from ..utils.hashing import full_request_hash, prefix_hash, stable_dict_hash
from ..utils.logging import get_logger

log = get_logger("cache")


class CacheStore:
    """统一缓存接口：strip 进/读出/写回。"""

    def __init__(self, cfg: CacheCfg):
        self.cfg = cfg
        self._lock = asyncio.Lock()
        self._mem: dict[str, tuple[float, dict]] = {}
        self._db_path = Path(cfg.db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_ready = False

    async def init(self) -> None:
        if self.cfg.backend != "sqlite" or self._db_ready:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS response_cache(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS prefix_stats(
                    prefix_key TEXT PRIMARY KEY,
                    input_tokens INTEGER DEFAULT 0,
                    hit_count INTEGER DEFAULT 0,
                    expires_at REAL NOT NULL
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS ix_resp_exp ON response_cache(expires_at)")
            await db.commit()
        self._db_ready = True

    # === cache_control 剥离 ===
    @staticmethod
    def strip_cache_control(payload: dict) -> dict:
        """递归移除请求里所有 cache_control 字段（MiniMax 不识别）。"""
        return _strip_recursive(payload)

    # === 响应缓存 ===
    async def get_response(self, payload: dict) -> dict | None:
        key = full_request_hash(payload)
        now = time.time()
        if self.cfg.backend == "memory":
            ent = self._mem.get(key)
            if ent and ent[0] > now:
                log.info(f"[mem-cache HIT] {key[:12]}")
                return ent[1]
            return None
        await self.init()
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT value FROM response_cache WHERE key=? AND expires_at>?", (key, now)
            ) as cur:
                row = await cur.fetchone()
        if row:
            log.info(f"[sqlite-cache HIT] {key[:12]}")
            return json.loads(row[0])
        return None

    async def put_response(self, payload: dict, response: dict, *, ttl: int | None = None) -> None:
        ttl = ttl or self.cfg.default_ttl
        key = full_request_hash(payload)
        now = time.time()
        expires = now + ttl
        if self.cfg.backend == "memory":
            self._mem[key] = (expires, response)
            await self._evict_memory()
            return
        await self.init()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO response_cache(key,value,expires_at,created_at) VALUES(?,?,?,?)",
                (key, json.dumps(response, ensure_ascii=False), expires, now),
            )
            await db.commit()
        await self._gc_sqlite()

    # === 前缀缓存（用于注入 cache_read_input_tokens 占位）===
    async def touch_prefix(self, messages: list[dict], system: Any, tools: list[dict] | None,
                          input_tokens: int) -> tuple[int, int]:
        """返回 (cache_creation, cache_read)，用于回填 usage."""
        if not self.cfg.enabled:
            return 0, 0
        key = prefix_hash(messages, system, tools)
        now = time.time()
        await self.init()
        if self.cfg.backend == "memory":
            ent = self._mem.get(f"prefix:{key}")
            if ent and ent[0] > now:
                self._mem[f"prefix:{key}"] = (now + self.cfg.long_ttl, ent[1])
                return 0, int(ent[1].get("input_tokens", 0) * 0.9)
            self._mem[f"prefix:{key}"] = (now + self.cfg.long_ttl, {"input_tokens": input_tokens})
            return input_tokens, 0
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT input_tokens, hit_count FROM prefix_stats WHERE prefix_key=? AND expires_at>?",
                (key, now),
            ) as cur:
                row = await cur.fetchone()
            if row:
                await db.execute(
                    "UPDATE prefix_stats SET hit_count=hit_count+1, expires_at=? WHERE prefix_key=?",
                    (now + self.cfg.long_ttl, key),
                )
                await db.commit()
                return 0, int(row[0] * 0.9)
            await db.execute(
                "INSERT OR REPLACE INTO prefix_stats(prefix_key,input_tokens,hit_count,expires_at) VALUES(?,?,?,?)",
                (key, input_tokens, 0, now + self.cfg.long_ttl),
            )
            await db.commit()
        return input_tokens, 0

    # === 内部辅助 ===
    async def _evict_memory(self) -> None:
        if len(self._mem) <= self.cfg.max_entries:
            return
        # 按过期时间排序，删 1/4
        items = sorted(self._mem.items(), key=lambda kv: kv[1][0])
        for k, _ in items[: max(1, len(items) // 4)]:
            self._mem.pop(k, None)

    async def _gc_sqlite(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM response_cache WHERE expires_at < ?", (time.time(),))
            await db.commit()


def _strip_recursive(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_recursive(v) for k, v in obj.items() if k != "cache_control"}
    if isinstance(obj, list):
        return [_strip_recursive(x) for x in obj]
    return obj
