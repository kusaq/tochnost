"""Timing / grace configuration for RSHR processing (env-backed defaults)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class RshrTimingConfig:
    tail_grace_sec: float = 120.0
    post2_match_grace_sec: float = 30.0
    max_rail_open_sec: float = 3600.0
    cycle_end_zero_packets: int = 2
    reorder_buffer_ms: float = 500.0
    max_late_packet_sec: float = 300.0
    late_append_grace_sec: float = 180.0
    max_tightening_window_sec: float = 180.0
    # Мин. длительность импульса лазера post2 (отсекает ложный depart)
    post2_min_segment_sec: float = 3.0
    # Макс. длительность проезда post1 (лазер ON→OFF); дольше — мусор, не в FIFO/post2
    post1_max_pass_sec: float = 2400.0
    # Норма ~200 гаек на ~25 м; вне диапазона — запись в error, не правим «органику»
    screws_count_min_ok: int = 160
    screws_count_max_ok: int = 220

    @classmethod
    def from_env(cls) -> RshrTimingConfig:
        return cls(
            tail_grace_sec=_env_float("TAIL_GRACE_SEC", 120.0),
            post2_match_grace_sec=_env_float("POST2_MATCH_GRACE_SEC", 30.0),
            max_rail_open_sec=_env_float("MAX_RAIL_OPEN_SEC", 3600.0),
            cycle_end_zero_packets=_env_int("CYCLE_END_ZERO_PACKETS", 2),
            reorder_buffer_ms=_env_float("REORDER_BUFFER_MS", 500.0),
            max_late_packet_sec=_env_float("MAX_LATE_PACKET_SEC", 300.0),
            late_append_grace_sec=_env_float("LATE_APPEND_GRACE_SEC", 180.0),
            max_tightening_window_sec=_env_float("MAX_TIGHTENING_WINDOW_SEC", 180.0),
            post2_min_segment_sec=_env_float("POST2_MIN_SEGMENT_SEC", 3.0),
            post1_max_pass_sec=_env_float("POST1_MAX_PASS_SEC", 2400.0),
            screws_count_min_ok=_env_int("SCREWS_COUNT_MIN_OK", 160),
            screws_count_max_ok=_env_int("SCREWS_COUNT_MAX_OK", 220),
        )

    @classmethod
    def capture_faithful(cls) -> RshrTimingConfig:
        """Offline replay on ordered JSONL — minimal buffering."""
        return cls(
            reorder_buffer_ms=0.0,
            cycle_end_zero_packets=1,
            max_late_packet_sec=float("inf"),
        )

    @classmethod
    def live_stress(cls) -> RshrTimingConfig:
        """Stricter reorder / debounce for synthetic jitter tests."""
        return cls(
            reorder_buffer_ms=500.0,
            cycle_end_zero_packets=2,
            max_late_packet_sec=300.0,
        )
