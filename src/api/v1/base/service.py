from dataclasses import dataclass

from infra.timescale_db.uow import TimeScaleDBUnitOfWork
from infra.redis.redis_api import RedisAPI


@dataclass(slots=True)
class BaseService:
    uow: TimeScaleDBUnitOfWork
    redis: RedisAPI | None = None
