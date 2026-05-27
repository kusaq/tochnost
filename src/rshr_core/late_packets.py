"""Late / out-of-order packet classification (FSM does not roll back)."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from rshr_core.config import RshrTimingConfig


class LatePacketPolicy(str, Enum):
    NORMAL = "normal"
    LATE_APPEND = "late_append"
    STALE = "stale"


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
    """
    if now is None:
        now = datetime.utcnow()

    if config.max_late_packet_sec != float("inf"):
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
