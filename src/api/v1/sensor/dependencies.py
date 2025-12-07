from typing import AsyncIterator, Annotated

from fastapi import Depends

from api.v1.sensor.service import SensorService
from infra.redis.dependencies import RedisDep
from infra.timescale_db.uow import TimeScaleDBUnitOfWorkDep
from api.v1.sensor.state import SensorStateDep


async def get_sensor_service(
    uow: TimeScaleDBUnitOfWorkDep,
    redis: RedisDep,
    state: SensorStateDep,
) -> AsyncIterator[SensorService]:
    service = SensorService(
        uow=uow,
        redis=redis,
    )
    service.state = state
    yield service


SensorServiceDep = Annotated[SensorService, Depends(get_sensor_service)]
