from fastapi import APIRouter, Response, status

from api.v1.sensor.dependencies import SensorServiceDep
from api.v1.sensor.schemas import Sensor1Create, Sensor2Create, Sensor1Read
from api.v1.sensor.state import SensorStateDep
from api.v1.base.dependencies import PaginationDep

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


@router.get(
    "/rail/{rail_id}/sensor1",
    response_model=list[Sensor1Read],
    summary="Показания Sensor1 по рельсе",
    description="Возвращает список записей Sensor1 для заданной рельсы по возрастанию идентификатора. Поддерживает пагинацию.",
)
async def list_sensor1_by_rail(
    rail_id: int,
    pagination: PaginationDep,
    sensor_service: SensorServiceDep,
):
    limit = pagination.limit if pagination.limit is not None else 20
    offset = pagination.offset or 0
    return await sensor_service.list_sensor1_by_rail(rail_id=rail_id, limit=limit, offset=offset)
