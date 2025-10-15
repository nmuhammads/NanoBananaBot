from typing import Optional

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