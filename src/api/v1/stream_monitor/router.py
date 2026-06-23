import asyncio
import json

from fastapi import APIRouter, Query, Response, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

from api.v1.stream_monitor.schemas import (
    CorrelationGroupRead,
    CorrelationGroupsResponse,
    StreamEventCreate,
    StreamEventRead,
    StreamEventsListResponse,
    StreamMonitorStats,
)
from api.v1.stream_monitor.service import stream_monitor
from api.v1.stream_monitor.state import STREAM_MONITOR_STATE

router = APIRouter(prefix="/stream-monitor", tags=["Stream Monitor"])


@router.post(
    "/events",
    response_model=StreamEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Принять событие потока",
    description="Сохраняет событие в буфер монитора и рассылает подписчикам WebSocket. Авторизация не требуется.",
)
async def ingest_stream_event(body: StreamEventCreate) -> StreamEventRead:
    event = await stream_monitor.record_event(
        source=body.source,
        payload=body.payload,
        event_type=body.event_type,
        event_ts=body.event_ts,
        rshr_id=body.rshr_id,
        correlation_id=body.correlation_id,
        summary=body.summary,
    )
    return StreamEventRead(**stream_monitor.event_dict(event))


@router.get(
    "/events",
    response_model=StreamEventsListResponse,
    summary="История событий потока",
    description="Возвращает последние сохранённые события с фильтрами. Авторизация не требуется.",
)
async def list_stream_events(
    limit: int = Query(default=100, ge=1, le=1000),
    source: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    rshr_id: int | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    problems_only: bool = Query(default=False),
) -> StreamEventsListResponse:
    items = [
        StreamEventRead(**item)
        for item in stream_monitor.get_recent(
            limit=limit,
            source=source,
            event_type=event_type,
            rshr_id=rshr_id,
            correlation_id=correlation_id,
            problems_only=problems_only,
        )
    ]
    return StreamEventsListResponse(items=items, total_stored=STREAM_MONITOR_STATE.get_stats()["stored_count"])


@router.get(
    "/groups",
    response_model=CorrelationGroupsResponse,
    summary="Группы связанных событий РШР",
    description="Возвращает события, сгруппированные по correlation_id. Авторизация не требуется.",
)
async def list_correlation_groups(
    limit: int = Query(default=50, ge=1, le=200),
) -> CorrelationGroupsResponse:
    items = [CorrelationGroupRead(**g) for g in stream_monitor.get_correlation_groups(limit=limit)]
    return CorrelationGroupsResponse(items=items)


@router.get(
    "/stats",
    response_model=StreamMonitorStats,
    summary="Статистика потока",
    description="Счётчики принятых событий, здоровье датчиков и активные подписчики. Авторизация не требуется.",
)
async def stream_monitor_stats() -> StreamMonitorStats:
    return StreamMonitorStats(**stream_monitor.get_stats())


async def _run_stream_sender(ws: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        event = await queue.get()
        if ws.client_state != WebSocketState.CONNECTED:
            break
        message = {"type": "event", "data": event}
        try:
            await ws.send_text(json.dumps(message, ensure_ascii=False))
        except Exception:
            # Соединение оборвалось/зависло — выходим, чтобы хэндлер закрыл WS
            # и фронт переподключился (и заново получил snapshot).
            break


async def _run_stream_receiver(ws: WebSocket) -> None:
    while True:
        try:
            await ws.receive_text()
        except WebSocketDisconnect:
            break
        except Exception:
            break


@router.websocket("/ws")
async def stream_monitor_ws(websocket: WebSocket) -> None:
    """
    Реалтайм-канал монитора потока.
    При подключении отправляет snapshot последних событий и статистику,
    затем транслирует новые события по мере поступления.
    """
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    STREAM_MONITOR_STATE.subscribe(queue)

    try:
        snapshot = {
            "type": "snapshot",
            "events": stream_monitor.get_recent(limit=300),
            "stats": stream_monitor.get_stats(),
            "groups": stream_monitor.get_correlation_groups(limit=30),
        }
        await websocket.send_text(json.dumps(snapshot, ensure_ascii=False, default=str))

        sender_task = asyncio.create_task(_run_stream_sender(websocket, queue))
        receiver_task = asyncio.create_task(_run_stream_receiver(websocket))
        try:
            # Завершаемся, как только умирает любая из сторон: отправитель
            # (обрыв/зависание send) или приёмник (клиент отключился).
            await asyncio.wait(
                {sender_task, receiver_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (sender_task, receiver_task):
                task.cancel()
            for task in (sender_task, receiver_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    finally:
        STREAM_MONITOR_STATE.unsubscribe(queue)


@router.delete(
    "/events",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Очистить буфер событий",
    description="Сбрасывает in-memory историю монитора. Авторизация не требуется.",
)
async def clear_stream_events() -> Response:
    await STREAM_MONITOR_STATE.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
