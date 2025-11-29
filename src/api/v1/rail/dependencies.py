from typing import AsyncIterator, Annotated

from fastapi import Depends

from api.v1.rail.service import RailService
from infra.timescale_db.uow import TimeScaleDBUnitOfWorkDep
from infra.redis.dependencies import RedisDep


async def get_rail_service(
    uow: TimeScaleDBUnitOfWorkDep,
    redis: RedisDep,
) -> AsyncIterator[RailService]:
    yield RailService(uow=uow, redis=redis)


RailServiceDep = Annotated[RailService, Depends(get_rail_service)]


