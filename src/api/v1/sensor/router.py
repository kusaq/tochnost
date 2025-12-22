from fastapi import APIRouter, Response, status

from api.v1.sensor.schemas import Sensor1Create, Sensor2Create
from api.v1.sensor.state import SensorStateDep

router = APIRouter(prefix="/sensor", tags=["Sensor"])


@router.post("/first", status_code=status.HTTP_202_ACCEPTED, summary="Буферизованная запись Sensor1")
async def save_first_sensor_data(
    sensor_data: Sensor1Create,
    # sensor_service: SensorServiceDep,
    state: SensorStateDep,
) -> Response:
    # Вставляем в очередь для асинхронной обработки воркерами
    await state.sensor1_queue().put(sensor_data)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/second", status_code=status.HTTP_202_ACCEPTED, summary="Буферизованная запись Sensor2")
async def save_second_sensor_data(
    sensor_data: Sensor2Create,
    # sensor_service: SensorServiceDep,
    state: SensorStateDep,
) -> Response:
    # Вставляем в очередь для асинхронной обработки воркерами
    await state.sensor2_queue().put(sensor_data)
    return Response(status_code=status.HTTP_202_ACCEPTED)
