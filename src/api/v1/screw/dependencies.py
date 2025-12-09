from typing import AsyncIterator, Annotated

from fastapi import Depends

from api.v1.screw.service import ScrewService
from infra.timescale_db.uow import TimeScaleDBUnitOfWorkDep
from infra.redis.dependencies import RedisDep


async def get_screw_service(
    uow: TimeScaleDBUnitOfWorkDep,
    redis: RedisDep,
) -> AsyncIterator[ScrewService]:
    yield ScrewService(uow=uow, redis=redis)


ScrewServiceDep = Annotated[ScrewService, Depends(get_screw_service)]
