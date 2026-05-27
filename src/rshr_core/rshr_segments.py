"""Laser segment builder shared by validate / match / simulate / backend."""

from __future__ import annotations

from typing import Any, Callable

from rshr_core.rshr_length import classify_length_mm, segment_length_mm, should_discard_rshr


def laser_on(values: dict[str, Any]) -> bool:
    left = values.get("laserOnRailLeft", values.get("laser_on_rail_left", False))
    right = values.get("laserOnRailRight", values.get("laser_on_rail_right", False))
    return bool(left or right)


def mm_along(values: dict[str, Any]) -> int:
    return int(values.get("mmAlongRail", values.get("mm_along_rail", 0)))


def finalize_segment(current: dict[str, Any]) -> dict[str, Any]:
    length = segment_length_mm(current["start_mm"], current["max_mm"])
    kind = classify_length_mm(length)
    return {
        "start_ts": current["start_ts"],
        "end_ts": current.get("end_ts"),
        "start_mm": current["start_mm"],
        "max_mm": current["max_mm"],
        "length_mm": length,
        "length_m": round(length / 1000, 2),
        "length_class": kind,
        "discarded": should_discard_rshr(length),
        "records": current["records"],
        "unique_mm_count": len(current.get("unique_mm", set())),
    }


def build_laser_segments(
    records: list[tuple[Any, dict[str, Any]]],
    *,
    ts_key: Callable[[Any], Any] | None = None,
    values_key: Callable[[Any], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Build laser ON segments from chronological records.

    Each record is (timestamp, values) or a dict with timestamp/values keys.
    """
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for item in records:
        if isinstance(item, tuple):
            ts, values = item
        else:
            ts = item.get("timestamp") if ts_key is None else ts_key(item)
            values = item.get("values", {}) if values_key is None else values_key(item)

        on = laser_on(values)
        mm = mm_along(values)

        if on:
            if current is None:
                current = {
                    "start_ts": ts,
                    "end_ts": ts,
                    "start_mm": mm,
                    "max_mm": mm,
                    "records": 1,
                    "unique_mm": {mm},
                }
            else:
                current["end_ts"] = ts
                current["max_mm"] = max(current["max_mm"], mm)
                current["records"] += 1
                current["unique_mm"].add(mm)
        elif current is not None:
            segments.append(finalize_segment(current))
            current = None

    if current is not None:
        segments.append(finalize_segment(current))

    return segments


def filter_valid_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in segments if not s.get("discarded")]
