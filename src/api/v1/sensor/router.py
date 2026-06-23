from datetime import datetime, timezone

from fastapi import APIRouter, Response, status, HTTPException
import asyncio
import logging

from api.v1.sensor.dependencies import SensorServiceDep
from api.v1.sensor.schemas import Sensor1Create, Sensor2Create, Sensor1Read, SensorStateResetRequest
from api.v1.sensor.state import SensorStateDep, MergedSensorEvent
from api.v1.base.dependencies import PaginationDep
from api.v1.stream_monitor.service import stream_monitor
from api.v1.ws.service import cache_dashboard_env_stats
from infra.redis.dependencies import RedisDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sensor", tags=["Sensor"])

# Держим сильные ссылки на фоновые задачи записи в монитор: иначе asyncio
# хранит только слабые ссылки и задача может быть собрана GC до завершения.
_monitor_tasks: set[asyncio.Task] = set()


def _record_monitor_event(event: MergedSensorEvent) -> None:
    task = asyncio.create_task(stream_monitor.record_merged_sensor_event(event))
    _monitor_tasks.add(task)
    task.add_done_callback(_on_monitor_task_done)


def _on_monitor_task_done(task: asyncio.Task) -> None:
    _monitor_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("stream monitor recording failed: %r", exc)


def _enqueue(state, event: MergedSensorEvent) -> None:
    try:
        state.merged_queue().put_nowait(event)
    except asyncio.QueueFull:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sensor ingestion queue full",
        )


@router.post("/first", status_code=status.HTTP_202_ACCEPTED, summary="Буферизованная запись Sensor1")
async def save_first_sensor_data(
    sensor_data: Sensor1Create,
    state: SensorStateDep,
) -> Response:
    event = MergedSensorEvent(
        event_ts=sensor_data.timestamp,
        kind="s1",
        payload=sensor_data,
        received_at=datetime.now(timezone.utc),
    )
    _enqueue(state, event)
    _record_monitor_event(event)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post(
    "/state/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Сброс SENSOR_STATE",
    description="Обнуляет in-memory состояние датчиков (активная рельса, очереди, статистика). "
    "Требует confirm=true. Используйте для восстановления после сбоев или тестов.",
    responses={400: {"description": "Требуется confirm=true"}},
)
async def reset_sensor_state(
    body: SensorStateResetRequest,
    state: SensorStateDep,
) -> Response:
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Требуется confirm=true для выполнения сброса",
        )
    state.reset()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/second", status_code=status.HTTP_202_ACCEPTED, summary="Буферизованная запись Sensor2")
async def save_second_sensor_data(
    sensor_data: Sensor2Create,
    state: SensorStateDep,
    redis: RedisDep,
) -> Response:
    await cache_dashboard_env_stats(
        redis,
        sensor_data.values.temperature,
        sensor_data.values.humidity,
    )
    event = MergedSensorEvent(
        event_ts=sensor_data.timestamp,
        kind="s2",
        payload=sensor_data,
        received_at=datetime.now(timezone.utc),
    )
    _enqueue(state, event)
    _record_monitor_event(event)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get(
    "/debug/state",
    summary="Снимок состояния FSM датчиков",
    description="Текущее in-memory состояние конвейера РШР (активная рельса, очереди поста 2, "
    "счётчики пакетов, статус worker'ов). Для удалённой диагностики. Авторизация не требуется.",
)
async def sensor_debug_state(state: SensorStateDep) -> dict:
    from api.v1.sensor.service import get_worker_status

    snapshot = state.debug_snapshot()
    snapshot["workers"] = get_worker_status()
    snapshot["generated_at"] = datetime.now(timezone.utc).isoformat()
    return snapshot


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
