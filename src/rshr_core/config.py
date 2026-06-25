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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class RshrTimingConfig:
    tail_grace_sec: float = 120.0
    max_rail_open_sec: float = 3600.0
    cycle_end_zero_packets: int = 2
    # Мин. пауза между циклами закрутки: повторный импульс момента раньше этого окна
    # после конца предыдущего цикла — это доворот той же шпалы, а не новый цикл.
    # Защищает от «2 закрутки с быстрым перерывом» (живой путь, не только offline).
    min_inter_cycle_sec: float = 5.0
    reorder_buffer_ms: float = 500.0
    max_late_packet_sec: float = 300.0
    # Отбрасывать «старые» пакеты по абсолютному возрасту (received_at − event_ts)?
    # По умолчанию ВЫКЛ: при дрейфе часов ПЛК/сканера это глушило бы весь поток.
    # Защита от out-of-order остаётся за per-stream watermark (он дрейф-инвариантен).
    drop_stale_by_received_at: bool = False
    late_append_grace_sec: float = 180.0
    max_tightening_window_sec: float = 180.0
    # Мин. длительность импульса лазера post2 (отсекает ложный depart)
    post2_min_segment_sec: float = 3.0
    # Макс. длительность проезда post1 (лазер ON→OFF); дольше — мусор, не в FIFO/post2
    post1_max_pass_sec: float = 2400.0
    # Мин. продвижение mm_along_rail для подтверждения реального РШР (отсекает руку под лазером)
    laser_confirm_advance_mm: int = 200
    # Мин. длительность пропадания лазера поста 1, после которой возврат лазера+сброс mm
    # трактуется как НОВЫЙ рельс. Короче — это мигание/глитч энкодера на одном рельсе,
    # рельс не раскалываем (защита от фантомных РШР).
    post1_min_laser_off_sec: float = 1.5
    # Норма ~200 гаек на ~25 м; вне диапазона — запись в error, не правим «органику»
    screws_count_min_ok: int = 160
    screws_count_max_ok: int = 220

    @classmethod
    def from_env(cls) -> RshrTimingConfig:
        return cls(
            tail_grace_sec=_env_float("TAIL_GRACE_SEC", 120.0),
            max_rail_open_sec=_env_float("MAX_RAIL_OPEN_SEC", 3600.0),
            cycle_end_zero_packets=_env_int("CYCLE_END_ZERO_PACKETS", 2),
            min_inter_cycle_sec=_env_float("MIN_INTER_CYCLE_SEC", 5.0),
            reorder_buffer_ms=_env_float("REORDER_BUFFER_MS", 500.0),
            max_late_packet_sec=_env_float("MAX_LATE_PACKET_SEC", 300.0),
            drop_stale_by_received_at=_env_bool("DROP_STALE_BY_RECEIVED_AT", False),
            late_append_grace_sec=_env_float("LATE_APPEND_GRACE_SEC", 180.0),
            max_tightening_window_sec=_env_float("MAX_TIGHTENING_WINDOW_SEC", 180.0),
            post2_min_segment_sec=_env_float("POST2_MIN_SEGMENT_SEC", 3.0),
            post1_max_pass_sec=_env_float("POST1_MAX_PASS_SEC", 2400.0),
            laser_confirm_advance_mm=_env_int("LASER_CONFIRM_ADVANCE_MM", 200),
            post1_min_laser_off_sec=_env_float("POST1_MIN_LASER_OFF_SEC", 1.5),
            screws_count_min_ok=_env_int("SCREWS_COUNT_MIN_OK", 160),
            screws_count_max_ok=_env_int("SCREWS_COUNT_MAX_OK", 220),
        )

    @classmethod
    def capture_faithful(cls) -> RshrTimingConfig:
        """Offline replay on ordered JSONL — minimal buffering."""
        return cls(
            reorder_buffer_ms=0.0,
            cycle_end_zero_packets=1,
            min_inter_cycle_sec=0.0,
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
