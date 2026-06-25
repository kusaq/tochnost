"""Late / out-of-order packet classification (FSM does not roll back)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from rshr_core.config import RshrTimingConfig


class LatePacketPolicy(str, Enum):
    NORMAL = "normal"
    LATE_APPEND = "late_append"
    STALE = "stale"


def _naive_utc(dt: datetime | None) -> datetime | None:
    """Приводит datetime к naive UTC, чтобы безопасно сравнивать aware и naive метки."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def classify_late_packet(
    event_ts: datetime,
    *,
    watermark: datetime | None,
    rail_start: datetime | None,
    rail_end: datetime | None,
    rail_closed: bool,
    config: RshrTimingConfig,
    now: datetime | None = None,
) -> LatePacketPolicy:
    """
    Classify packet relative to processing watermark and rail lifecycle.

    - NORMAL: in-order within open rail window
    - LATE_APPEND: closed rail, event within [start, end + late_append_grace]
    - STALE: too old vs watermark or beyond max_late_packet_sec

    Все метки приводятся к naive UTC: ``received_at`` приходит aware, а ``event_ts``
    нормализован в naive — вычитание разнотипных datetime роняло worker (TypeError).
    """
    event_ts = _naive_utc(event_ts)
    watermark = _naive_utc(watermark)
    rail_start = _naive_utc(rail_start)
    rail_end = _naive_utc(rail_end)
    now = _naive_utc(now) or datetime.utcnow()

    if config.drop_stale_by_received_at and config.max_late_packet_sec != float("inf"):
        # ВНИМАНИЕ: age = received_at(сервер) − event_ts(устройство) включает В СЕБЯ
        # дрейф часов ПЛК/сканера, а не только задержку доставки. Поэтому по умолчанию
        # этот отброс ВЫКЛЮЧЕН (drop_stale_by_received_at=False) — иначе рассинхрон NTP
        # глушил бы весь поток. Защита от реального out-of-order — ниже, по per-stream
        # watermark (он дрейф-инвариантен). Включать только при гарантированном NTP.
        age_sec = (now - event_ts).total_seconds()
        if age_sec > config.max_late_packet_sec:
            return LatePacketPolicy.STALE

    if watermark is not None and event_ts < watermark - timedelta(milliseconds=config.reorder_buffer_ms):
        if rail_closed and rail_start is not None and rail_end is not None:
            grace_end = rail_end + timedelta(seconds=config.late_append_grace_sec)
            if rail_start <= event_ts <= grace_end:
                return LatePacketPolicy.LATE_APPEND
        return LatePacketPolicy.STALE

    if rail_closed and rail_start is not None and rail_end is not None:
        grace_end = rail_end + timedelta(seconds=config.late_append_grace_sec)
        if event_ts > rail_end and event_ts <= grace_end:
            return LatePacketPolicy.LATE_APPEND

    return LatePacketPolicy.NORMAL
