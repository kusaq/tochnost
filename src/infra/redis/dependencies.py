from typing import AsyncIterator, Annotated

from fastapi import Depends

from infra.redis.redis_api import RedisAPI


async def get_redis() -> AsyncIterator[RedisAPI]:
    redis_client = RedisAPI()
    try:
        yield redis_client
    finally:
        await redis_client.close()

RedisDep = Annotated[RedisAPI, Depends(get_redis)]
