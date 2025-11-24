from fastapi import APIRouter

from api.v1.auth.dependencies import CurrentUserDep
from api.v1.sensor.service import SensorService
from api.v1.sensor.schemas import Sensor1Create, Sensor2Create

router = APIRouter(prefix="/sensor", tags=["Sensor"])


@router.post("/first")
async def save_first_sensor_data(
    sensor_data: Sensor1Create,
    auth_service: SensorService,
    user: CurrentUserDep
) -> None:
    ...


@router.post("/second")
async def save_second_sensor_data(
    sensor_data: Sensor2Create,
    auth_service: SensorService,
    user: CurrentUserDep
) -> None:
    ...
