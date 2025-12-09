from typing import AsyncIterator, Annotated

from fastapi import Depends

from api.v1.error.service import ErrorService
from infra.timescale_db.uow import TimeScaleDBUnitOfWorkDep
from infra.redis.dependencies import RedisDep


async def get_error_service(
    uow: TimeScaleDBUnitOfWorkDep,
    redis: RedisDep,
) -> AsyncIterator[ErrorService]:
    yield ErrorService(uow=uow, redis=redis)


ErrorServiceDep = Annotated[ErrorService, Depends(get_error_service)]
