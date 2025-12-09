from typing import AsyncIterator, Annotated

from fastapi import Depends

from api.v1.threshold.service import ThresholdService
from infra.timescale_db.uow import TimeScaleDBUnitOfWorkDep
from infra.redis.dependencies import RedisDep


async def get_threshold_service(
    uow: TimeScaleDBUnitOfWorkDep,
    redis: RedisDep,
) -> AsyncIterator[ThresholdService]:
    yield ThresholdService(uow=uow, redis=redis)


ThresholdServiceDep = Annotated[ThresholdService, Depends(get_threshold_service)]
