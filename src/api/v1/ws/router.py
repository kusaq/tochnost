import asyncio
from typing import Sequence

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from api.v1.sensor.state import SensorStateDep
from infra.redis.dependencies import RedisDep
from api.v1.ws.service import run_sender, run_push_stats, run_push_status, send_errors_today_distribution
from api.v1.ws.schemas import (
    WSDocsOverview,
    DashboardStatsEnvelope,
    DashboardStatusEnvelope,
    DashboardErrorsEnvelope,
    DashboardStagesEnvelope,
    ErrorsDistributionEnvelope,
    DashboardStatsData,
    DashboardStatusData,
    DashboardErrorData,
    DashboardStagesData,
    ErrorsDistributionData,
    ErrorsDistributionBucket,
    EmptyPayload,
)

router = APIRouter(tags=["WebSocket"])

@router.get(
    "/ws/docs",
    response_model=WSDocsOverview,
    summary="Документация по WebSocket-каналу дашборда",
    description=(
        "Описание формата сообщений и каналов WebSocket-подключения к дашборду. "
        "Подключение выполняется к пути `/api/v1/ws/dashboard`. "
        "Даты передаются в ISO 8601, enum — строковыми значениями. "
        "Если активной рельсы нет, в каналах `status` и `stages` данные — пустой объект `{}`."
    ),
)
async def ws_docs_overview() -> WSDocsOverview:
    return WSDocsOverview(url="/api/v1/ws/dashboard")


@router.websocket("/ws/dashboard")
async def dashboard_ws(
    websocket: WebSocket,
    redis: RedisDep,
    sensor: SensorStateDep,
    channels: Sequence[str] | None = Query(
        default=None,
        description="Список каналов Redis для подписки. По умолчанию подписывается на стандартные каналы дашборда.",
    ),
):
    """
    Реалтайм канал для дашборда.
    Подписывается на каналы Redis и ретранслирует события фронту.

    Ожидаемые стандартные каналы:
    - dashboard:stats      — блок статистики (рельсы за сегодня, рельсы в час, время на единицу, ошибки за сегодня, текущие T/H)
    - dashboard:status     — блок статуса (активная рельса)
    - dashboard:errors     — блок ошибок (время + ошибка)
    - dashboard:stages     — блок этапов текущей рельсы (гайки слева/справа, сопротивление текущее/среднее)
    """
    await websocket.accept()
    await send_errors_today_distribution(websocket)
    default_channels = ["dashboard:errors", "dashboard:stages"]
    subs = list(channels) if channels else default_channels

    async with asyncio.TaskGroup() as tg:
        tg.create_task(run_sender(websocket, redis, subs))
        tg.create_task(run_push_stats(websocket, redis))
        tg.create_task(run_push_status(websocket))
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                await asyncio.sleep(1)


@router.get(
    "/ws/schema/stats",
    response_model=DashboardStatsEnvelope,
    summary="Схема сообщения dashboard:stats",
    description="Агрегированная статистика дашборда.",
)
async def ws_schema_stats() -> DashboardStatsEnvelope:
    return DashboardStatsEnvelope(
        data=DashboardStatsData(
            temperature_current="N/A",
            humidity_current="N/A",
            errors_count=0,
            rails_today=0,
            rails_per_hour=0,
            avg_speed_per_hour=0.0,
        )
    )


@router.get(
    "/ws/schema/status",
    response_model=DashboardStatusEnvelope,
    summary="Схема сообщения dashboard:status",
    description="Статус активной рельсы. При отсутствии активной рельсы data = {}.",
)
async def ws_schema_status(example: bool = Query(default=True, description="Вернуть пример с данными (true) или пустой объект (false)")) -> DashboardStatusEnvelope:
    if not example:
        return DashboardStatusEnvelope(data=EmptyPayload())
    return DashboardStatusEnvelope(
        data=DashboardStatusData(
            rail_id=123,
            name="Рельса #123",
            status="В процессе",
            object_name="Участок А",
            fastening_type="Клеммное",
            start_time=None,
            end_time=None,
        )
    )


@router.get(
    "/ws/schema/errors",
    response_model=DashboardErrorsEnvelope,
    summary="Схема сообщения dashboard:errors",
    description="Событие об ошибке по любой метрике.",
)
async def ws_schema_errors() -> DashboardErrorsEnvelope:
    return DashboardErrorsEnvelope(
        data=DashboardErrorData(
            timestamp="2025-12-13T12:00:00+00:00",
            description="Гайка №10 по правой стороне была излишне закручена",
            value_name="frequency_torque",
            value=780.0,
        )
    )


@router.get(
    "/ws/schema/stages",
    response_model=DashboardStagesEnvelope,
    summary="Схема сообщения dashboard:stages",
    description="Этапы по активной рельсе; при её отсутствии data = {}.",
)
async def ws_schema_stages(example: bool = Query(default=True, description="Вернуть пример с данными (true) или пустой объект (false)")) -> DashboardStagesEnvelope:
    if not example:
        return DashboardStagesEnvelope(data=EmptyPayload())
    return DashboardStagesEnvelope(
        data=DashboardStagesData(
            errors_count=2,
            mm_side_wear_left=0.4,
            mm_side_wear_left_ok=True,
            mm_side_wear_right=0.7,
            mm_side_wear_right_ok=False,
            screws_completed=16,
            resistance=48.2,
            resistance_ok=True,
            mm_gauge=1522.3,
            mm_gauge_ok=True,
            mm_gauge_avg=1521.8,
        )
    )


@router.get(
    "/ws/schema/errors-distribution",
    response_model=ErrorsDistributionEnvelope,
    summary="Схема сообщения dashboard:errors_distribution",
    description="Одноразовая сводка распределения ошибок за сегодня по часам.",
)
async def ws_schema_errors_distribution() -> ErrorsDistributionEnvelope:
    return ErrorsDistributionEnvelope(
        data=ErrorsDistributionData(
            **{
                "from": "2025-12-13T00:00:00+00:00",
                "to": "2025-12-13T12:34:56+00:00",
                "buckets": [
                    ErrorsDistributionBucket(hour="2025-12-13T10:00:00+00:00", count=3),
                    ErrorsDistributionBucket(hour="2025-12-13T11:00:00+00:00", count=1),
                ],
                "total": 4,
            }
        )
    )