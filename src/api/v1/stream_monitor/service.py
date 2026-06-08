from datetime import datetime
from typing import Any

from api.v1.sensor.state import MergedSensorEvent
from api.v1.stream_monitor.state import STREAM_MONITOR_STATE, StoredStreamEvent, event_to_dict


class StreamMonitorService:
    def __init__(self) -> None:
        self._state = STREAM_MONITOR_STATE

    async def record_event(
        self,
        source: str,
        payload: dict[str, Any],
        *,
        event_type: str = "manual",
        event_ts: datetime | None = None,
        rshr_id: int | None = None,
        correlation_id: str | None = None,
        summary: str | None = None,
    ) -> StoredStreamEvent:
        return await self._state.add_event(
            source=source,
            payload=payload,
            event_type=event_type,
            event_ts=event_ts,
            rshr_id=rshr_id,
            correlation_id=correlation_id,
            summary=summary,
        )

    async def record_pipeline_event(
        self,
        event_type: str,
        *,
        rshr_id: int | None = None,
        payload: dict[str, Any] | None = None,
        event_ts: datetime | None = None,
        summary: str | None = None,
        source: str = "pipeline",
    ) -> StoredStreamEvent:
        return await self._state.add_event(
            source=source,
            event_type=event_type,
            payload=payload or {},
            event_ts=event_ts,
            rshr_id=rshr_id,
            summary=summary,
        )

    async def record_merged_sensor_event(self, event: MergedSensorEvent) -> StoredStreamEvent:
        if hasattr(event.payload, "model_dump"):
            payload = event.payload.model_dump(mode="json")
        else:
            payload = dict(event.payload)

        if event.kind == "s1":
            sensor_id = int(getattr(event.payload, "sensor_id", 1))
            source = "sensor1_post1" if sensor_id == 1 else "sensor1_post2"
        else:
            source = "modbus"

        mm = payload.get("values", {}).get("mm_along_rail") if isinstance(payload.get("values"), dict) else None
        laser_left = payload.get("values", {}).get("laser_on_rail_left") if isinstance(payload.get("values"), dict) else None
        summary = f"mm={mm}" if mm is not None else None
        if laser_left is not None:
            summary = f"{summary or ''} laser L={laser_left}".strip()

        return await self._state.add_event(
            source=source,
            event_type="sensor_raw",
            payload=payload,
            event_ts=event.event_ts,
            received_at=event.received_at,
            summary=summary or "Сырые данные датчика",
        )

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
        return self._state.get_recent(
            limit=limit,
            source=source,
            event_type=event_type,
            rshr_id=rshr_id,
            correlation_id=correlation_id,
            problems_only=problems_only,
        )

    def get_stats(self) -> dict[str, Any]:
        stats = self._state.get_stats()
        return stats

    def get_correlation_groups(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._state.get_correlation_groups(limit=limit)

    def event_dict(self, event: StoredStreamEvent) -> dict[str, Any]:
        return event_to_dict(event)


stream_monitor = StreamMonitorService()
