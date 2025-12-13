import asyncio
from typing import Sequence

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from api.v1.sensor.state import SensorStateDep
from infra.redis.dependencies import RedisDep
from api.v1.ws.service import run_sender, run_push_stats


router = APIRouter(tags=["WebSocket"])


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
    default_channels = ["dashboard:status", "dashboard:errors", "dashboard:stages"]
    subs = list(channels) if channels else default_channels

    async with asyncio.TaskGroup() as tg:
        tg.create_task(run_sender(websocket, redis, subs))
        tg.create_task(run_push_stats(websocket, redis))
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                await asyncio.sleep(1)