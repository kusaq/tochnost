"""Хуки монитора потока в конвейере обработки РШР."""

from datetime import datetime
from typing import Any

from api.v1.stream_monitor.service import stream_monitor


async def emit_pipeline_event(
    event_type: str,
    *,
    rshr_id: int | None = None,
    payload: dict[str, Any] | None = None,
    event_ts: datetime | None = None,
    summary: str | None = None,
) -> None:
    try:
        await stream_monitor.record_pipeline_event(
            event_type,
            rshr_id=rshr_id,
            payload=payload,
            event_ts=event_ts,
            summary=summary,
        )
    except Exception:
        pass
