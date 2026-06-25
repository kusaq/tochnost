import os
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, Any

import asyncio
from fastapi import Depends

STALE_AFTER_SEC = 30
SENSOR_SOURCES = ("sensor1_post1", "sensor1_post2", "modbus")

# Сырой firehose (sensor_raw) и pipeline-события хранятся РАЗДЕЛЬНО, иначе
# высокочастотный Sensor1/Modbus за минуты вытесняет редкие rshr_opened /
# tightening_* / rshr_closed из общего буфера, и экспорт pipeline отдаёт обрезки.
# Оба размера — на ENV, меняются без пересборки образа.


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


# Сырой буфер (sensor_raw + всё подряд для live-firehose).
MAX_EVENTS = _env_int("STREAM_MONITOR_MAX_EVENTS", 5000)
# Durable-буфер ТОЛЬКО pipeline-событий (низкий поток → большой запас).
MAX_PIPELINE_EVENTS = _env_int("STREAM_MONITOR_MAX_PIPELINE_EVENTS", 20000)
# Типы событий, которые НЕ относятся к pipeline (не попадают в durable-буфер).
RAW_EVENT_TYPES = frozenset({"sensor_raw"})


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(slots=True)
class StoredStreamEvent:
    id: int
    source: str
    event_type: str
    payload: dict[str, Any]
    received_at: datetime
    event_ts: datetime | None = None
    rshr_id: int | None = None
    correlation_id: str | None = None
    summary: str | None = None


@dataclass(slots=True)
class SensorHealthRecord:
    source: str
    label: str
    last_seen_at: datetime | None = None
    events_count: int = 0
    events_last_minute: int = 0
    is_stale: bool = True
    stale_after_sec: int = STALE_AFTER_SEC


class StreamMonitorState:
    def __init__(
        self,
        max_events: int = MAX_EVENTS,
        max_subscribers: int = 50,
        max_pipeline_events: int = MAX_PIPELINE_EVENTS,
    ) -> None:
        # Сырой firehose: sensor_raw + pipeline вперемешку (live-вкладка, mode=full).
        self._events: deque[StoredStreamEvent] = deque(maxlen=max_events)
        # Durable-буфер: только pipeline-события. Сырой Modbus/Sensor1 его не трогает,
        # поэтому rshr_opened → … → rshr_closed не вытесняется потоком и доступен для
        # экспорта/incident/групп/фильтров даже спустя часы активной закрутки.
        self._pipeline_events: deque[StoredStreamEvent] = deque(maxlen=max_pipeline_events)
        self._next_id = 0
        self._subscribers: set[asyncio.Queue] = set()
        self._max_subscribers = max_subscribers
        self._lock = asyncio.Lock()
        self._total_received = 0
        self._by_source: Counter[str] = Counter()
        self._by_event_type: Counter[str] = Counter()
        self._last_received_at: datetime | None = None
        self._sensor_health: dict[str, SensorHealthRecord] = {
            "sensor1_post1": SensorHealthRecord(source="sensor1_post1", label="Датчик 1 · пост 1"),
            "sensor1_post2": SensorHealthRecord(source="sensor1_post2", label="Датчик 1 · пост 2"),
            "modbus": SensorHealthRecord(source="modbus", label="Modbus · закрутка"),
        }
        self._sensor_recent_ts: dict[str, deque[datetime]] = {
            src: deque(maxlen=500) for src in SENSOR_SOURCES
        }

    def subscribe(self, queue: asyncio.Queue) -> None:
        if len(self._subscribers) >= self._max_subscribers:
            raise RuntimeError("Too many stream monitor subscribers")
        self._subscribers.add(queue)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _touch_sensor(self, source: str, at: datetime) -> None:
        if source not in self._sensor_health:
            return
        rec = self._sensor_health[source]
        rec.last_seen_at = _as_utc(at)
        rec.events_count += 1
        self._sensor_recent_ts[source].append(at)
        cutoff = at.timestamp() - 60
        while self._sensor_recent_ts[source] and self._sensor_recent_ts[source][0].timestamp() < cutoff:
            self._sensor_recent_ts[source].popleft()
        rec.events_last_minute = len(self._sensor_recent_ts[source])

    def _is_stale(self, rec: SensorHealthRecord, now: datetime) -> bool:
        if rec.last_seen_at is None:
            return True
        return (_as_utc(now) - _as_utc(rec.last_seen_at)).total_seconds() > rec.stale_after_sec

    def get_sensor_health(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        items: list[dict[str, Any]] = []
        for rec in self._sensor_health.values():
            is_stale = self._is_stale(rec, now)
            gap_sec: float | None = None
            if rec.last_seen_at is not None:
                gap_sec = round((_as_utc(now) - _as_utc(rec.last_seen_at)).total_seconds(), 1)
            items.append(
                {
                    "source": rec.source,
                    "label": rec.label,
                    "last_seen_at": _as_utc(rec.last_seen_at) if rec.last_seen_at else None,
                    "events_count": rec.events_count,
                    "events_last_minute": rec.events_last_minute,
                    "is_stale": is_stale,
                    "is_healthy": not is_stale,
                    "stale_after_sec": rec.stale_after_sec,
                    "gap_sec": gap_sec,
                }
            )
        return items

    async def add_event(
        self,
        source: str,
        payload: dict[str, Any],
        *,
        event_type: str = "unknown",
        event_ts: datetime | None = None,
        received_at: datetime | None = None,
        rshr_id: int | None = None,
        correlation_id: str | None = None,
        summary: str | None = None,
    ) -> StoredStreamEvent:
        now = _as_utc(received_at) if received_at else datetime.now(timezone.utc)
        if correlation_id is None and rshr_id is not None:
            correlation_id = f"rshr:{rshr_id}"

        async with self._lock:
            self._next_id += 1
            event = StoredStreamEvent(
                id=self._next_id,
                source=source,
                event_type=event_type,
                payload=payload,
                received_at=now,
                event_ts=event_ts,
                rshr_id=rshr_id,
                correlation_id=correlation_id,
                summary=summary,
            )
            self._events.append(event)
            if event_type not in RAW_EVENT_TYPES:
                # Дублируем pipeline-событие в durable-буфер. Память на дубль
                # ничтожна, зато сырой поток не может его выселить.
                self._pipeline_events.append(event)
            self._total_received += 1
            self._by_source[source] += 1
            self._by_event_type[event_type] += 1
            self._last_received_at = now
            if source in self._sensor_health:
                self._touch_sensor(source, now)

        self._broadcast(event)
        return event

    def _broadcast(self, event: StoredStreamEvent) -> None:
        message = event_to_dict(event)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Медленный подписчик (фоновая вкладка / просадка сети): сбрасываем
                # самые старые события, чтобы освободить место под новое. Подписку
                # НЕ удаляем — иначе при живом WS монитор молча перестаёт получать
                # данные навсегда, пока страницу не перезагрузят.
                self._drop_oldest_and_put(queue, message)

    @staticmethod
    def _drop_oldest_and_put(queue: asyncio.Queue, message: dict[str, Any]) -> None:
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                queue.put_nowait(message)
                return
            except asyncio.QueueFull:
                continue

    def get_recent(
        self,
        limit: int = 100,
        *,
        source: str | None = None,
        event_type: str | None = None,
        rshr_id: int | None = None,
        correlation_id: str | None = None,
        problems_only: bool = False,
    ) -> list[dict[str, Any]]:
        # Если фильтр нацелен на pipeline (конкретная РШР, проблемы, группа,
        # источник pipeline или не-сырой тип) — ищем в durable-буфере, чтобы
        # старые события не оказались уже вытесненными сырым потоком.
        pipeline_query = (
            problems_only
            or rshr_id is not None
            or correlation_id is not None
            or source == "pipeline"
            or (event_type is not None and event_type not in RAW_EVENT_TYPES)
        )
        base = self._pipeline_events if pipeline_query else self._events
        items = list(base)
        if source:
            items = [ev for ev in items if ev.source == source]
        if event_type:
            items = [ev for ev in items if ev.event_type == event_type]
        if rshr_id is not None:
            items = [ev for ev in items if ev.rshr_id == rshr_id]
        if correlation_id:
            items = [ev for ev in items if ev.correlation_id == correlation_id]
        if problems_only:
            problem_types = {
                "rshr_discarded",
                "post2_unmatched",
                "packet_stale",
                "modbus_skipped",
            }
            items = [
                ev
                for ev in items
                if ev.event_type in problem_types or (ev.event_type == "rshr_closed" and ev.payload.get("discarded"))
            ]
        if limit < len(items):
            items = items[-limit:]
        return [event_to_dict(ev) for ev in items]

    def export_events(self, *, mode: str = "pipeline") -> list[dict[str, Any]]:
        """События буфера для выгрузки.

        mode=pipeline — durable-буфер pipeline-событий (полная история конвейера,
        сырой поток её не вытесняет); mode=full — сырой firehose (sensor_raw +
        pipeline, ограничен MAX_EVENTS).
        """
        if mode == "pipeline":
            items = list(self._pipeline_events)
        else:
            items = list(self._events)
        return [event_to_dict(ev) for ev in items]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_received": self._total_received,
            "stored_count": len(self._events),
            "pipeline_stored_count": len(self._pipeline_events),
            "pipeline_capacity": self._pipeline_events.maxlen,
            "subscribers": len(self._subscribers),
            "by_source": dict(self._by_source),
            "by_event_type": dict(self._by_event_type),
            "last_received_at": _as_utc(self._last_received_at) if self._last_received_at else None,
            "sensor_health": self.get_sensor_health(),
            "stale_after_sec": STALE_AFTER_SEC,
        }

    def get_correlation_groups(self, limit: int = 50) -> list[dict[str, Any]]:
        groups: dict[str, list[StoredStreamEvent]] = {}
        # Группы строим по durable-буферу: correlation_id есть только у
        # pipeline-событий, а сырой firehose всё равно их вытеснил бы.
        for ev in reversed(self._pipeline_events):
            if not ev.correlation_id:
                continue
            bucket = groups.setdefault(ev.correlation_id, [])
            if len(bucket) < 200:
                bucket.append(ev)
        result: list[dict[str, Any]] = []
        for cid, events in list(groups.items())[:limit]:
            events_sorted = sorted(events, key=lambda e: e.id)
            rshr_id = next((e.rshr_id for e in events_sorted if e.rshr_id is not None), None)
            result.append(
                {
                    "correlation_id": cid,
                    "rshr_id": rshr_id,
                    "event_count": len(events_sorted),
                    "first_at": events_sorted[0].received_at.isoformat(),
                    "last_at": events_sorted[-1].received_at.isoformat(),
                    "event_types": list(dict.fromkeys(e.event_type for e in events_sorted)),
                    "events": [event_to_dict(e) for e in events_sorted[-20:]],
                }
            )
        return result

    async def clear(self) -> None:
        async with self._lock:
            self._events.clear()
            self._pipeline_events.clear()
            self._by_source.clear()
            self._by_event_type.clear()
            for rec in self._sensor_health.values():
                rec.last_seen_at = None
                rec.events_count = 0
                rec.events_last_minute = 0
            for dq in self._sensor_recent_ts.values():
                dq.clear()


def event_to_dict(event: StoredStreamEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "source": event.source,
        "event_type": event.event_type,
        "payload": event.payload,
        "received_at": event.received_at.isoformat(),
        "event_ts": event.event_ts.isoformat() if event.event_ts else None,
        "rshr_id": event.rshr_id,
        "correlation_id": event.correlation_id,
        "summary": event.summary,
    }


STREAM_MONITOR_STATE = StreamMonitorState()


def get_stream_monitor_state() -> StreamMonitorState:
    return STREAM_MONITOR_STATE


StreamMonitorStateDep = Annotated[StreamMonitorState, Depends(get_stream_monitor_state)]
