"""Short-term conversation memory backed by Redis lists.

Key layout:  aia:{tenant}:{agent}:conv:{peer}  -> list of JSON messages
A rolling window (default 20 turns) is kept; older turns are summarised into
long-term memory by the agent before eviction.
"""
from __future__ import annotations

import json
from functools import lru_cache

import redis.asyncio as redis

from ..config import get_settings


class ShortTermMemory:
    def __init__(self, window: int = 20, ttl_seconds: int = 60 * 60 * 24 * 7):
        self._r = redis.from_url(get_settings().redis_url, decode_responses=True)
        self.window = window
        self.ttl = ttl_seconds

    def _key(self, tenant: str, agent: str, peer: str) -> str:
        return f"aia:{tenant}:{agent}:conv:{peer}"

    async def append(self, tenant: str, agent: str, peer: str, role: str, content: str) -> None:
        key = self._key(tenant, agent, peer)
        await self._r.rpush(key, json.dumps({"role": role, "content": content}))
        await self._r.ltrim(key, -self.window, -1)
        await self._r.expire(key, self.ttl)

    async def history(self, tenant: str, agent: str, peer: str) -> list[dict]:
        raw = await self._r.lrange(self._key(tenant, agent, peer), 0, -1)
        return [json.loads(x) for x in raw]

    async def clear(self, tenant: str, agent: str, peer: str) -> None:
        await self._r.delete(self._key(tenant, agent, peer))


@lru_cache
def get_short_term() -> ShortTermMemory:
    return ShortTermMemory()
