import asyncio
import redis.asyncio as redis
from contextlib import suppress

from core.config import settings


class RedisAPI:
    _pool: redis.ConnectionPool = redis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=200,
        decode_responses=True,
    )

    def __init__(self):
        self._client = redis.Redis(connection_pool=self._pool)

    async def close(self):
        await self._client.aclose()

    async def set(self, key: str, value: str, expire: int | None = 0):
        await self._client.set(name=key, value=value, ex=expire or None)

    async def get(self, key: str) -> str | None:
        return await self._client.get(name=key)

    async def delete(self, key: str):
        await self._client.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self._client.exists(key))

    async def incr(self, key: str) -> int:
        return await self._client.incr(key)

    async def expire(self, key: str, seconds: int) -> bool:
        return await self._client.expire(key, seconds)

    async def publish(self, channel: str, message: str) -> int:
        return await self._client.publish(channel, message)

    async def iter_pubsub(self, channel: str):
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for msg in pubsub.listen():
                if msg and msg.get("type") == "message":
                    yield msg.get("data")
        finally:
            with suppress(Exception, asyncio.CancelledError):
                await pubsub.unsubscribe(channel)
                await pubsub.close()

    async def iter_pubsub_multi(self, channels: list[str]):
        pubsub = self._client.pubsub()
        await pubsub.subscribe(*channels)
        try:
            async for msg in pubsub.listen():
                if msg and msg.get("type") == "message":
                    yield msg.get("channel"), msg.get("data")
        finally:
            with suppress(Exception, asyncio.CancelledError):
                await pubsub.unsubscribe(*channels)
                await pubsub.close()
