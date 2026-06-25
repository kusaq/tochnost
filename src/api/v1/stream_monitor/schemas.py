from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StreamEventCreate(BaseModel):
    source: str = Field(default="manual", max_length=64, description="Источник события")
    event_type: str = Field(default="manual", max_length=64, description="Тип события")
    payload: dict[str, Any] = Field(default_factory=dict, description="Произвольные данные события")
    event_ts: datetime | None = Field(default=None, description="Временная метка события (если известна)")
    rshr_id: int | None = Field(default=None, description="ID РШР")
    correlation_id: str | None = Field(default=None, description="ID группы связанных событий")
    summary: str | None = Field(default=None, description="Краткое описание")


class StreamEventRead(BaseModel):
    id: int
    source: str
    event_type: str
    payload: dict[str, Any]
    received_at: datetime
    event_ts: datetime | None = None
    rshr_id: int | None = None
    correlation_id: str | None = None
    summary: str | None = None


class SensorHealthRead(BaseModel):
    source: str
    label: str
    last_seen_at: datetime | None = None
    events_count: int
    events_last_minute: int
    is_stale: bool
    is_healthy: bool
    stale_after_sec: int
    gap_sec: float | None = None


class StreamMonitorStats(BaseModel):
    total_received: int
    stored_count: int
    pipeline_stored_count: int = 0
    pipeline_capacity: int | None = None
    subscribers: int
    by_source: dict[str, int]
    by_event_type: dict[str, int] = Field(default_factory=dict)
    last_received_at: datetime | None = None
    sensor_health: list[SensorHealthRead] = Field(default_factory=list)
    stale_after_sec: int = 30


class StreamEventsListResponse(BaseModel):
    items: list[StreamEventRead]
    total_stored: int


class CorrelationGroupRead(BaseModel):
    correlation_id: str
    rshr_id: int | None = None
    event_count: int
    first_at: str
    last_at: str
    event_types: list[str]
    events: list[StreamEventRead]


class CorrelationGroupsResponse(BaseModel):
    items: list[CorrelationGroupRead]
