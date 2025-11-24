from typing import AsyncIterator, Annotated

from fastapi import Depends

from api.v1.sensor.service import SensorService
from infra.redis.dependencies import RedisDep
from infra.timescale_db.uow import TimeScaleDBUnitOfWorkDep


async def get_sensor_service(
    uow: TimeScaleDBUnitOfWorkDep,
    redis: RedisDep,
) -> AsyncIterator[SensorService]:
    yield SensorService(
        uow=uow,
        redis=redis,
    )


SensorServiceDep = Annotated[SensorService, Depends(get_sensor_service)]
