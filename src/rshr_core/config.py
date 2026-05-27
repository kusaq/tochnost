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
