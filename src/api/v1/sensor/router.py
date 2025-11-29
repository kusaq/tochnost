from fastapi import APIRouter

from api.v1.sensor.dependencies import SensorServiceDep
from api.v1.sensor.manager import SensorManagerDep
from api.v1.sensor.schemas import Sensor1Create, Sensor2Create

router = APIRouter(prefix="/sensor", tags=["Sensor"])


@router.post("/first")
async def save_first_sensor_data(
    sensor_data: Sensor1Create,
    sensor_service: SensorServiceDep,
    manager: SensorManagerDep
) -> None:
    await sensor_service.add_sensor1_data(sensor_data, manager)


@router.post("/second")
async def save_second_sensor_data(
    sensor_data: Sensor2Create,
    sensor_service: SensorServiceDep
) -> None:
    await sensor_service.add_sensor2_data(sensor_data)
