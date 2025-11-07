from typing import Optional, Any

import json
import redis.asyncio as redis


class Cache:
    def __init__(self, redis_url: str):
        self._client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    # --- Balance helpers (legacy) ---
    async def get_balance(self, user_id: int) -> int:
        value = await self._client.get(f"nbalance:{user_id}")
        return int(value) if value is not None else 0

    async def set_balance(self, user_id: int, tokens: int) -> None:
        await self._client.set(f"nbalance:{user_id}", int(tokens))

    async def increment_balance(self, user_id: int, delta: int) -> int:
        return await self._client.incrby(f"nbalance:{user_id}", int(delta))

    # --- Last generation payload ---
    async def set_last_generation_attempt(self, user_id: int, gen_id: int, payload: dict, ttl_seconds: int = 7 * 24 * 3600) -> None:
        """
        Stores exact request payload used for a generation attempt.

        Keys used:
        - nlastgen_attempt:{user_id}:{gen_id} -> JSON payload
        - nlastgen_last:{user_id} -> gen_id (pointer to latest)
        """
        try:
            key = f"nlastgen_attempt:{user_id}:{gen_id}"
            data = json.dumps(payload, ensure_ascii=False)
            await self._client.set(key, data, ex=int(ttl_seconds) if ttl_seconds and ttl_seconds > 0 else None)
            await self._client.set(f"nlastgen_last:{user_id}", str(gen_id))
        except Exception:
            # Non-fatal; logging left to callers
            pass

    async def get_last_generation_attempt(self, user_id: int) -> Optional[tuple[int, dict]]:
        """
        Returns (gen_id, payload dict) for the last stored attempt or None.
        """
        try:
            last_id_raw = await self._client.get(f"nlastgen_last:{user_id}")
            if not last_id_raw:
                return None
            try:
                gen_id = int(str(last_id_raw))
            except Exception:
                return None
            key = f"nlastgen_attempt:{user_id}:{gen_id}"
            data = await self._client.get(key)
            if not data:
                return None
            try:
                payload = json.loads(data)
            except Exception:
                return None
            if isinstance(payload, dict):
                return gen_id, payload
            return None
        except Exception:
            return None

    async def close(self) -> None:
        await self._client.close()