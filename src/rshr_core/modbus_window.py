"""Modbus tightening time window per rail."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from rshr_core.config import RshrTimingConfig

# PLC often emits M1–M4 peaks every ~8–9 s for one sleeper; real spacing is ~20+ s.
_MIN_INTER_CYCLE_SEC = 20.0
_STUCK_LASER_SEC = 30.0 * 60.0
_EXTENDED_TAIL_SEC = 240.0


def find_post2_next_start_after(
    after_ts: datetime,
    post2_valid_segments: list[dict[str, Any]],
) -> datetime | None:
    """First post2 valid segment start strictly after ``after_ts`` (= N+1 on post2)."""
    for seg in post2_valid_segments:
        t = seg["start_ts"]
        if t > after_ts:
            return t
    return None


def expected_sleeper_range(length_mm: int) -> tuple[int, int]:
    """Orienting sleeper count (~2.5–3.5 m spacing on ~25 m RSHR)."""
    if length_mm <= 0:
        return 0, 0
    lo = max(1, int(length_mm / 3500))
    hi = max(lo, int(length_mm / 2500) + 1)
    return lo, hi


def _max_span_td(length_mm: int) -> timedelta:
    sec = min(900.0, max(240.0, (length_mm / 1000.0) * 25.0))
    return timedelta(seconds=sec)


def compute_modbus_window(
    *,
    laser_on_start: datetime,
    laser_off_end: datetime,
    length_mm: int,
    post2_valid_segments: list[dict[str, Any]] | None = None,
    config: RshrTimingConfig | None = None,
) -> tuple[datetime, datetime, dict[str, Any]]:
    """
  Modbus tightening for rail N after post 1 laser goes off (post 2 tightening).

  Primary window: ``[laser_off, laser_off + tail_grace]``.

  Do not start at laser ON (measurement pass produces false cycles) and do not
  cap at post2 N+1 segment start — that is often ~50 s after laser off while
  tightening continues for minutes.
    """
    cfg = config or RshrTimingConfig.capture_faithful()
    tail = timedelta(seconds=cfg.tail_grace_sec)

    t_start = laser_off_end
    t_end = laser_off_end + tail
    laser_duration = (laser_off_end - laser_on_start).total_seconds()

    kind = "post1_laser_off_tail"
    meta: dict[str, Any] = {
        "modbus_window": kind,
        "laser_duration_sec": round(laser_duration, 1),
    }
    exp_lo, exp_hi = expected_sleeper_range(length_mm)
    if exp_lo:
        meta["sleepers_expected_lo"] = exp_lo
        meta["sleepers_expected_hi"] = exp_hi
    return t_start, t_end, meta


def _detect(
    modbus_events: list[tuple[Any, dict[str, Any]]],
    t0: datetime,
    t1: datetime,
    mm_at,
    *,
    min_inter_cycle_sec: float | None,
    **detect_kw,
) -> list:
    from rshr_core.tightening import detect_cycles_in_window

    return detect_cycles_in_window(
        modbus_events,
        t0,
        t1,
        mm_at,
        min_inter_cycle_sec=min_inter_cycle_sec,
        **detect_kw,
    )


def compute_modbus_window_with_fallback(
    modbus_events: list[tuple[Any, dict[str, Any]]],
    *,
    laser_on_start: datetime,
    laser_off_end: datetime,
    length_mm: int,
    post2_valid_segments: list[dict[str, Any]] | None = None,
    mm_at,
    config: RshrTimingConfig | None = None,
    **detect_kw,
) -> tuple[list, dict[str, Any]]:
    cfg = config or RshrTimingConfig.capture_faithful()
    t0, t1, meta = compute_modbus_window(
        laser_on_start=laser_on_start,
        laser_off_end=laser_off_end,
        length_mm=length_mm,
        post2_valid_segments=post2_valid_segments,
        config=cfg,
    )

    exp_lo = meta.get("sleepers_expected_lo", 0)
    exp_hi = meta.get("sleepers_expected_hi", 99)
    laser_duration = meta.get("laser_duration_sec", 0.0)
    max_span = _max_span_td(length_mm)
    tail = timedelta(seconds=cfg.tail_grace_sec)

    def run_window(w0: datetime, w1: datetime, gap: float | None) -> list:
        return _detect(modbus_events, w0, w1, mm_at, min_inter_cycle_sec=gap, **detect_kw)

    cycles = run_window(t0, t1, None)
    kind = meta["modbus_window"]

    if exp_lo and len(cycles) < exp_lo:
        t_end_ext = laser_off_end + timedelta(seconds=_EXTENDED_TAIL_SEC)
        cycles_ext = run_window(laser_off_end, t_end_ext, None)
        if len(cycles_ext) > len(cycles):
            cycles = cycles_ext
            t0, t1 = laser_off_end, t_end_ext
            kind = "post1_laser_off_tail_extended"

    if exp_lo and len(cycles) < exp_lo and laser_duration >= _STUCK_LASER_SEC:
        w0 = max(laser_on_start, laser_off_end - max_span)
        cycles_laser = run_window(w0, laser_off_end + tail, None)
        if len(cycles_laser) > len(cycles):
            cycles = cycles_laser
            t0, t1 = w0, laser_off_end + tail
            kind = "post1_stuck_laser_tail"

    if exp_hi and len(cycles) > exp_hi:
        cycles_gap = run_window(t0, t1, _MIN_INTER_CYCLE_SEC)
        if exp_lo <= len(cycles_gap) <= exp_hi or len(cycles_gap) < len(cycles):
            cycles = cycles_gap
            meta["min_inter_cycle_sec"] = _MIN_INTER_CYCLE_SEC

    meta["modbus_window"] = kind
    meta["modbus_t_start"] = t0.isoformat()
    meta["modbus_t_end"] = t1.isoformat()
    meta["sleepers_count"] = len(cycles)
    if exp_lo and len(cycles) > exp_hi:
        meta["sleepers_count_warning"] = "above_expected"
    elif exp_lo and len(cycles) < exp_lo:
        meta["sleepers_count_warning"] = "below_expected"

    return cycles, meta
