from typing import Optional, Any
import json

import redis.asyncio as redis


class Cache:
    def __init__(self, redis_url: str):
        self._client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def get_balance(self, user_id: int) -> int:
        value = await self._client.get(f"nbalance:{user_id}")
        return int(value) if value is not None else 0

    async def set_balance(self, user_id: int, tokens: int) -> None:
        await self._client.set(f"nbalance:{user_id}", int(tokens))

    async def increment_balance(self, user_id: int, delta: int) -> int:
        return await self._client.incrby(f"nbalance:{user_id}", int(delta))

    async def close(self) -> None:
        await self._client.close()

    # --- Last generation caching ---
    async def set_attempt_meta(self, user_id: int, generation_id: int, meta: dict, ttl_seconds: int = 7 * 24 * 3600) -> None:
        key = f"nlastgen_attempt:{user_id}:{generation_id}"
        await self._client.set(key, json.dumps(meta, ensure_ascii=False), ex=int(ttl_seconds))

    async def get_attempt_meta(self, user_id: int, generation_id: int) -> Optional[dict]:
        key = f"nlastgen_attempt:{user_id}:{generation_id}"
        raw = await self._client.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    async def set_last_success_meta(self, user_id: int, meta: dict) -> None:
        key = f"nlastgen_success:{user_id}"
        await self._client.set(key, json.dumps(meta, ensure_ascii=False))

    async def get_last_success_meta(self, user_id: int) -> Optional[dict]:
        key = f"nlastgen_success:{user_id}"
        raw = await self._client.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None