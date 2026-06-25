from collections import deque
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Annotated, Literal

from fastapi import Depends

from api.v1.sensor.schemas import RailSession, Screw as ScrewDC
from rshr_core.tightening import MOMENT_KEYS, FREQ_KEYS, bump_peaks


@dataclass
class TighteningCycleState:
    active: bool = False
    cycle_start_mm: int = 0
    max_moment: dict[str, float] = field(default_factory=lambda: {k: 0.0 for k in MOMENT_KEYS})
    max_freq: dict[str, float] = field(default_factory=lambda: {k: 0.0 for k in FREQ_KEYS})
    last_values: dict[str, Any] = field(default_factory=dict)
    zero_streak: int = 0


@dataclass
class Post2Tracker:
    """FIFO matching post1 rails ↔ post2 laser segments."""

    fifo_rail_ids: list[int] = field(default_factory=list)
    rail_at_post2: int | None = None
    post2_laser_on: bool = False
    post2_segment_index: int = 0
    unmatched_segments: int = 0
    last_laser_off_at: datetime | None = None
    # Кандидат сегмента: фронт ON зафиксирован, выпуск из FIFO откладывается до подтверждения
    pending_segment: bool = False
    pending_start_mm: int | None = None
    pending_start_ts: datetime | None = None

    def enqueue_opened_rail(self, rail_id: int) -> None:
        self.fifo_rail_ids.append(rail_id)

    def remove_from_fifo(self, rail_id: int) -> None:
        self.fifo_rail_ids = [x for x in self.fifo_rail_ids if x != rail_id]

    def on_post2_segment_start(self) -> int | None:
        """New laser segment on post2 — previous rail departs. Returns departed rail_id."""
        if not self.fifo_rail_ids:
            self.unmatched_segments += 1
            self.post2_segment_index += 1
            self.post2_laser_on = True
            return None
        departed = self.rail_at_post2
        self.rail_at_post2 = self.fifo_rail_ids.pop(0)
        self.post2_segment_index += 1
        self.post2_laser_on = True
        return departed


@dataclass
class PendingPost1Start:
    """Кандидат на старт РШР (пост 1): копим пакеты, пока движение не подтвердит реальный рельс."""

    start_mm: int
    start_ts: datetime
    last_mm: int
    buffer: list[Any] = field(default_factory=list)


@dataclass
class MergedSensorEvent:
    event_ts: datetime
    kind: Literal["s1", "s2"]
    payload: Any
    received_at: datetime


class SensorState:
    """
    Хранит оперативное состояние датчиков и рельсов между запросами (без доступа к БД).
    """

    def __init__(self, closed_keep_limit: int = 32) -> None:
        self._active: RailSession | None = None
        self._waiting_at_post2: dict[int, RailSession] = {}
        self._closed: Deque[RailSession] = deque(maxlen=closed_keep_limit)
        self._rail_screw_count: dict[int, int] = {}
        self._total_screws: int = 0
        self._screw_session: Deque[ScrewDC] = deque()
        self._merged_queue: asyncio.Queue = asyncio.Queue(maxsize=50000)
        self._sensor1_queue: asyncio.Queue = asyncio.Queue(maxsize=50000)
        self._sensor2_queue: asyncio.Queue = asyncio.Queue(maxsize=50000)
        self._bad_ranges: dict[str, tuple[int, float]] = {}
        self._res_sum: float = 0.0
        self._res_count: int = 0
        self._res_current: float = 0.0
        self._gauge_sum: float = 0.0
        self._gauge_count: int = 0
        self._temp_sum: float = 0.0
        self._temp_count: int = 0
        self._res_min: float | None = None
        self._res_max: float | None = None
        self._tightening = TighteningCycleState()
        self._tightening_rail_id: int | None = None
        # Живая позиция поста 2 (mmAlongRail сенсора sid=2) — «адрес шпалы» для
        # текущей закрутки. None, когда под лазером поста 2 нет рельса.
        self._post2_current_mm: int | None = None
        # Реестр шпал по рельсу: rail_id -> [{"pos": мм поста2, "screw_ids": [4]}].
        # Позволяет распознать повторную закрутку той же шпалы (обновить гайки,
        # не плодить дубль) и посчитать среднее расстояние между шпалами.
        self._rail_sleepers: dict[int, list[dict[str, Any]]] = {}
        self._post2 = Post2Tracker()
        self._post2_laser_was_on: bool = False
        self._modbus_skipped_no_post2: int = 0
        self._fsm_lock = asyncio.Lock()
        self._watermarks: dict[str, datetime] = {}
        # Перекос часов потока: received_at(сервер) − event_ts(устройство), по ключу потока.
        # Для диагностики дрейфа NTP на сканере/ПЛК (см. предупреждение в CLAUDE.md).
        self._stream_skew_sec: dict[str, float] = {}
        self._packets_reordered: int = 0
        self._packets_late_append: int = 0
        self._packets_stale: int = 0
        self._worker_errors: int = 0
        # Гайки по каналам для дашборда: rail_id -> {channel(1..4): {count, torque, ok}}
        self._dashboard_nuts: dict[int, dict[int, dict[str, Any]]] = {}
        # Последний снимок геометрии стадий (с поста 1), чтобы переиспользовать на посту 2
        self._last_stage_geometry: dict[str, Any] | None = None
        # Кандидат на старт РШР (пост 1): защита от ложного срабатывания лазера (рука под лазером)
        self._pending_post1: PendingPost1Start | None = None

    def merged_queue(self) -> asyncio.Queue:
        return self._merged_queue

    def sensor1_queue(self) -> asyncio.Queue:
        return self._sensor1_queue

    def sensor2_queue(self) -> asyncio.Queue:
        return self._sensor2_queue

    def fsm_lock(self) -> asyncio.Lock:
        return self._fsm_lock

    def get_watermark(self, key: str | None = None) -> datetime | None:
        if key is not None:
            return self._watermarks.get(key)
        candidates = list(self._watermarks.values())
        return max(candidates) if candidates else None

    def set_watermark(self, key: str, ts: datetime) -> None:
        current = self._watermarks.get(key)
        if current is None or ts > current:
            self._watermarks[key] = ts

    def mark_packet_reordered(self) -> None:
        self._packets_reordered += 1

    def mark_packet_late_append(self) -> None:
        self._packets_late_append += 1

    def record_stream_skew(self, key: str, skew_sec: float) -> None:
        self._stream_skew_sec[key] = skew_sec

    def mark_packet_stale(self) -> None:
        self._packets_stale += 1

    def mark_worker_error(self) -> None:
        self._worker_errors += 1

    def packet_counters(self) -> dict[str, int]:
        return {
            "packets_reordered": self._packets_reordered,
            "packets_late_append": self._packets_late_append,
            "packets_stale": self._packets_stale,
            "modbus_skipped_no_post2": self._modbus_skipped_no_post2,
            "worker_errors": self._worker_errors,
        }

    def debug_snapshot(self) -> dict[str, Any]:
        """Снимок текущего состояния FSM для удалённой диагностики."""

        def session_dict(s: RailSession | None) -> dict[str, Any] | None:
            if s is None:
                return None
            return {
                "rail_id": s.rail_id,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "last_timestamp": s.last_timestamp.isoformat() if s.last_timestamp else None,
                "start_mm_along_rail": s.start_mm_along_rail,
                "last_mm_along_rail": s.last_mm_along_rail,
                "laser_off_at": s.laser_off_at.isoformat() if s.laser_off_at else None,
                "post2_depart_at": s.post2_depart_at.isoformat() if s.post2_depart_at else None,
            }

        post2 = self._post2
        return {
            "active_rail": session_dict(self._active),
            "waiting_at_post2": {
                rail_id: session_dict(s) for rail_id, s in self._waiting_at_post2.items()
            },
            "closed_count": len(self._closed),
            "post2": {
                "fifo_rail_ids": list(post2.fifo_rail_ids),
                "rail_at_post2": post2.rail_at_post2,
                "post2_laser_on": post2.post2_laser_on,
                "post2_segment_index": post2.post2_segment_index,
                "unmatched_segments": post2.unmatched_segments,
            },
            "post2_laser_was_on": self._post2_laser_was_on,
            "watermarks": {key: ts.isoformat() for key, ts in self._watermarks.items()},
            "watermark": self.get_watermark().isoformat() if self.get_watermark() else None,
            "stream_skew_sec": dict(self._stream_skew_sec),
            "tightening_active": self._tightening.active,
            "tightening_rail_id": self._tightening_rail_id,
            "post2_current_mm": self._post2_current_mm,
            "sleepers_by_rail": {rid: len(v) for rid, v in self._rail_sleepers.items()},
            "rail_screw_count": dict(self._rail_screw_count),
            "merged_queue_size": self._merged_queue.qsize(),
            "packet_counters": self.packet_counters(),
        }

    def mark_modbus_skipped_no_post2(self) -> None:
        self._modbus_skipped_no_post2 += 1

    def post2_tracker(self) -> Post2Tracker:
        return self._post2

    def post2_laser_was_on(self) -> bool:
        return self._post2_laser_was_on

    def set_post2_laser_was_on(self, on: bool) -> None:
        self._post2_laser_was_on = on

    def has_active_rail(self) -> bool:
        return self._active is not None

    def get_active_rail(self) -> RailSession | None:
        return self._active

    def set_active(self, session: RailSession) -> None:
        self._active = session

    def clear_active(self) -> None:
        self._active = None

    def get_waiting_rail(self, rail_id: int) -> RailSession | None:
        return self._waiting_at_post2.get(rail_id)

    def park_at_post2(self, session: RailSession) -> None:
        self._waiting_at_post2[session.rail_id] = session

    def pop_waiting_rail(self, rail_id: int) -> RailSession | None:
        return self._waiting_at_post2.pop(rail_id, None)

    def waiting_rail_ids(self) -> list[int]:
        return list(self._waiting_at_post2.keys())

    def is_rail_waiting_at_post2(self, rail_id: int) -> bool:
        return rail_id in self._waiting_at_post2

    def find_rail_session(self, rail_id: int) -> RailSession | None:
        active = self.get_active_rail()
        if active and active.rail_id == rail_id:
            return active
        waiting = self.get_waiting_rail(rail_id)
        if waiting is not None:
            return waiting
        return self.find_closed_rail(rail_id)

    def update_active_progress(self, mm_along_rail: int, ts: datetime) -> None:
        if self._active:
            # Накопление пройденного пути: складываем только положительные приращения.
            # Сброс энкодера в 0 при мигании лазера даёт отрицательную дельту → её
            # игнорируем, и длина не теряется (сегменты сшиваются через сброс).
            delta = mm_along_rail - self._active.last_mm_along_rail
            if delta > 0:
                self._active.traversed_mm += delta
            self._active.last_mm_along_rail = mm_along_rail
            self._active.last_timestamp = ts

    def update_waiting_progress(self, rail_id: int, mm_along_rail: int, ts: datetime) -> None:
        waiting = self.get_waiting_rail(rail_id)
        if waiting:
            waiting.last_mm_along_rail = mm_along_rail
            waiting.last_timestamp = ts

    @property
    def has_screw_session(self) -> bool:
        return len(self._screw_session) > 0

    def clear_screw_session(self) -> None:
        self._screw_session.clear()

    @property
    def screw_session_len(self) -> int:
        return len(self._screw_session)

    def screw_session_item(self, index: int) -> ScrewDC:
        return self._screw_session[index]

    def append_screw(self, screw: ScrewDC) -> None:
        self._screw_session.append(screw)

    def update_screw_max_torque(self, index: int, new_value: float) -> None:
        current = self._screw_session[index].frequency_torque
        self._screw_session[index].frequency_torque = max(current, new_value)

    def iter_screws(self):
        return iter(self._screw_session)

    def is_bad_range_active(self, key: str) -> bool:
        return key in self._bad_ranges

    def open_bad_range(self, key: str, start_mm: int, start_value: float) -> None:
        if key not in self._bad_ranges:
            self._bad_ranges[key] = (start_mm, start_value)

    def close_bad_range(self, key: str) -> tuple[int, float] | None:
        opened = self._bad_ranges.pop(key, None)
        if opened is None:
            return None
        start_mm, start_value = opened
        return int(start_mm), float(start_value)

    def pop_all_bad_ranges(self) -> list[tuple[str, int, float]]:
        items = [(k, int(v[0]), float(v[1])) for k, v in self._bad_ranges.items()]
        self._bad_ranges.clear()
        return items

    def set_rail_screw_count(self, rail_id: int, count: int) -> None:
        self._rail_screw_count[rail_id] = int(count)

    def get_rail_screw_count(self, rail_id: int) -> int:
        return int(self._rail_screw_count.get(rail_id, 0))

    def increment_rail_screw_count(self, rail_id: int) -> int:
        n = self.get_rail_screw_count(rail_id) + 1
        self._rail_screw_count[rail_id] = n
        return n

    def clear_rail_screw_count(self, rail_id: int) -> None:
        self._rail_screw_count.pop(rail_id, None)

    def reset_total_screws(self) -> None:
        self._total_screws = 0

    def next_serial_for_rail(self, rail_id: int) -> int:
        return self.increment_rail_screw_count(rail_id)

    def next_serial(self) -> int:
        """Legacy: serial for active rail only."""
        active = self.get_active_rail()
        if active is None:
            self._total_screws += 1
            return self._total_screws
        return self.next_serial_for_rail(active.rail_id)

    def get_total_screws(self) -> int:
        active = self.get_active_rail()
        if active is not None:
            return self.get_rail_screw_count(active.rail_id)
        return self._total_screws

    def get_dashboard_screws(self) -> int:
        """Screws for dashboard: active post1 rail, else rail at post2."""
        active = self.get_active_rail()
        if active is not None:
            return self.get_rail_screw_count(active.rail_id)
        post2_id = self._post2.rail_at_post2
        if post2_id is not None:
            return self.get_rail_screw_count(post2_id)
        return 0

    def get_dashboard_rail_id(self) -> int | None:
        """РШР, которую показываем на дашборде: активная (пост 1), либо на посту 2, либо ждущая."""
        active = self.get_active_rail()
        if active is not None:
            return active.rail_id
        if self._post2.rail_at_post2 is not None:
            return self._post2.rail_at_post2
        if self._waiting_at_post2:
            return next(iter(self._waiting_at_post2))
        return None

    def record_nut_cycle(
        self,
        rail_id: int,
        per_channel_torque: dict[int, float],
        per_channel_ok: dict[int, bool],
        *,
        increment: bool = True,
    ) -> None:
        """Фиксирует цикл закрутки: при increment=True +1 гайка на канал; при повторной
        закрутке той же шпалы (increment=False) только обновляем момент/статус."""
        channels = self._dashboard_nuts.setdefault(
            rail_id, {ch: {"count": 0, "torque": 0.0, "ok": True} for ch in (1, 2, 3, 4)}
        )
        for ch in (1, 2, 3, 4):
            entry = channels[ch]
            if increment:
                entry["count"] = int(entry["count"]) + 1
            entry["torque"] = float(per_channel_torque.get(ch, entry["torque"]))
            entry["ok"] = bool(per_channel_ok.get(ch, True))

    def get_dashboard_nuts(self, rail_id: int | None) -> dict[int, dict[str, Any]]:
        if rail_id is None:
            return {ch: {"count": 0, "torque": 0.0, "ok": True} for ch in (1, 2, 3, 4)}
        return self._dashboard_nuts.get(
            rail_id, {ch: {"count": 0, "torque": 0.0, "ok": True} for ch in (1, 2, 3, 4)}
        )

    def clear_dashboard_nuts(self, rail_id: int) -> None:
        self._dashboard_nuts.pop(rail_id, None)

    def set_last_stage_geometry(self, geometry: dict[str, Any]) -> None:
        self._last_stage_geometry = dict(geometry)

    def get_last_stage_geometry(self) -> dict[str, Any] | None:
        return self._last_stage_geometry

    def clear_last_stage_geometry(self) -> None:
        self._last_stage_geometry = None

    def tightening_rail_id(self) -> int | None:
        return self._tightening_rail_id

    def set_tightening_rail_id(self, rail_id: int | None) -> None:
        self._tightening_rail_id = rail_id

    def update_resistance(self, value: float) -> None:
        v = float(value)
        self._res_current = v
        if v <= 0 or v > 65000:
            return
        self._res_sum += v
        self._res_count += 1
        if self._res_min is None or v < self._res_min:
            self._res_min = v
        if self._res_max is None or v > self._res_max:
            self._res_max = v

    def get_resistance_current(self) -> float:
        return float(self._res_current)

    def get_resistance_average(self) -> float:
        if self._res_count == 0:
            return 0.0
        return float(self._res_sum / self._res_count)

    def get_resistance_min(self) -> float | None:
        return self._res_min

    def get_resistance_max(self) -> float | None:
        return self._res_max

    def reset_resistance_stats(self) -> None:
        self._res_sum = 0.0
        self._res_count = 0
        self._res_current = 0.0
        self._res_min = None
        self._res_max = None

    def update_temperature(self, value: float) -> None:
        self._temp_sum += float(value)
        self._temp_count += 1

    def get_temperature_average(self) -> float:
        if self._temp_count == 0:
            return 0.0
        return float(self._temp_sum / self._temp_count)

    def reset_temperature_stats(self) -> None:
        self._temp_sum = 0.0
        self._temp_count = 0

    def reset_tightening_cycle(self) -> None:
        self._tightening = TighteningCycleState()
        self._tightening_rail_id = None

    def is_tightening_active(self) -> bool:
        return self._tightening.active

    # --- Позиция поста 2 и реестр шпал (дедуп повторной закрутки) ---
    def set_post2_current_mm(self, mm: int | None) -> None:
        self._post2_current_mm = mm

    def get_post2_current_mm(self) -> int | None:
        return self._post2_current_mm

    def find_sleeper(self, rail_id: int, pos: int, threshold_mm: int) -> dict[str, Any] | None:
        """Ближайшая уже записанная шпала рельса в пределах threshold_mm от pos —
        значит это та же шпала (повторная закрутка). None — новая шпала."""
        best = None
        best_d = threshold_mm
        for s in self._rail_sleepers.get(rail_id, []):
            d = abs(int(s["pos"]) - int(pos))
            if d < best_d:
                best_d = d
                best = s
        return best

    def register_sleeper(self, rail_id: int, pos: int, screw_ids: list[int]) -> None:
        self._rail_sleepers.setdefault(rail_id, []).append(
            {"pos": int(pos), "screw_ids": list(screw_ids)}
        )

    def rail_sleeper_positions(self, rail_id: int) -> list[int]:
        return sorted(int(s["pos"]) for s in self._rail_sleepers.get(rail_id, []))

    def rail_sleeper_count(self, rail_id: int) -> int:
        return len(self._rail_sleepers.get(rail_id, []))

    def clear_rail_sleepers(self, rail_id: int) -> None:
        self._rail_sleepers.pop(rail_id, None)

    def start_tightening_cycle(self, rail_id: int, mm_along_rail: int, values: Any) -> None:
        self._tightening_rail_id = rail_id
        self._tightening.active = True
        self._tightening.cycle_start_mm = int(mm_along_rail)
        self._tightening.max_moment = {k: 0.0 for k in MOMENT_KEYS}
        self._tightening.max_freq = {k: 0.0 for k in FREQ_KEYS}
        self._tightening.zero_streak = 0
        if hasattr(values, "model_dump"):
            self._tightening.last_values = values.model_dump()
        else:
            self._tightening.last_values = dict(values)
        bump_peaks(self._tightening.max_moment, self._tightening.max_freq, values)

    def bump_tightening_cycle(self, values: Any) -> None:
        if hasattr(values, "model_dump"):
            self._tightening.last_values = values.model_dump()
        else:
            self._tightening.last_values = dict(values)
        bump_peaks(self._tightening.max_moment, self._tightening.max_freq, values)

    def record_zero_torque_packet(self) -> int:
        self._tightening.zero_streak += 1
        return self._tightening.zero_streak

    def reset_zero_torque_streak(self) -> None:
        self._tightening.zero_streak = 0

    def finish_tightening_cycle(self) -> TighteningCycleState:
        finished = self._tightening
        self._tightening = TighteningCycleState()
        self._tightening_rail_id = None
        return finished

    def update_gauge(self, value: float) -> None:
        self._gauge_sum += float(value)
        self._gauge_count += 1

    def get_gauge_average(self) -> float:
        if self._gauge_count == 0:
            return 0.0
        return float(self._gauge_sum / self._gauge_count)

    def reset_gauge_stats(self) -> None:
        self._gauge_sum = 0.0
        self._gauge_count = 0

    def reset_laser_counts(self) -> None:
        self._laser_left_true_count = 0
        self._laser_right_true_count = 0

    def record_laser_flags(self, left_on_rail: bool, right_on_rail: bool) -> None:
        if not hasattr(self, "_laser_left_true_count"):
            self._laser_left_true_count = 0
            self._laser_right_true_count = 0
        if left_on_rail:
            self._laser_left_true_count += 1
        if right_on_rail:
            self._laser_right_true_count += 1

    def get_laser_counts(self) -> tuple[int, int]:
        if not hasattr(self, "_laser_left_true_count"):
            self._laser_left_true_count = 0
            self._laser_right_true_count = 0
        return int(self._laser_left_true_count), int(self._laser_right_true_count)

    def has_pending_post1(self) -> bool:
        return self._pending_post1 is not None

    def begin_pending_post1(self, data: Any) -> None:
        start_mm = int(data.values.mm_along_rail)
        self._pending_post1 = PendingPost1Start(
            start_mm=start_mm,
            start_ts=data.timestamp,
            last_mm=start_mm,
            buffer=[data],
        )

    def append_pending_post1(self, data: Any) -> None:
        if self._pending_post1 is None:
            return
        self._pending_post1.buffer.append(data)
        self._pending_post1.last_mm = int(data.values.mm_along_rail)

    def pending_post1_advance_mm(self) -> int:
        if self._pending_post1 is None:
            return 0
        return int(self._pending_post1.last_mm - self._pending_post1.start_mm)

    def take_pending_post1(self) -> PendingPost1Start | None:
        pending = self._pending_post1
        self._pending_post1 = None
        return pending

    def clear_pending_post1(self) -> None:
        self._pending_post1 = None

    def get_left_right_counts(self) -> tuple[int, int]:
        active = self.get_active_rail()
        if active is not None:
            total = self.get_rail_screw_count(active.rail_id)
        else:
            total = self._total_screws
        full_batches = total // 4
        rem = total % 4
        left = full_batches * 2 + min(2, rem)
        right = total - left
        return left, right

    def closed_len(self) -> int:
        return len(self._closed)

    def last_closed(self) -> RailSession | None:
        return None if len(self._closed) == 0 else self._closed[-1]

    def append_closed(self, session: RailSession) -> None:
        self._closed.append(session)

    def find_closed_rail(self, rail_id: int) -> RailSession | None:
        for session in self._closed:
            if session.rail_id == rail_id:
                return session
        return None

    def is_in_closed(self, ts: datetime) -> int | None:
        for session in reversed(self._closed):
            if ts < session.start_time:
                continue
            end_ts = session.end_time or session.last_timestamp or session.start_time
            if ts <= end_ts:
                return session.rail_id
            if ts > end_ts:
                break
        return None

    def reset(self, *, drain_queues: bool = True) -> None:
        self.clear_active()
        self._waiting_at_post2.clear()
        self._closed.clear()
        self._rail_screw_count.clear()
        self.clear_screw_session()
        self.reset_total_screws()
        self.reset_resistance_stats()
        self.reset_temperature_stats()
        self.reset_gauge_stats()
        self.reset_laser_counts()
        self.reset_tightening_cycle()
        self._post2 = Post2Tracker()
        self._post2_laser_was_on = False
        self._post2_current_mm = None
        self._rail_sleepers.clear()
        self._modbus_skipped_no_post2 = 0
        self._watermarks.clear()
        self._packets_reordered = 0
        self._packets_late_append = 0
        self._packets_stale = 0
        self._worker_errors = 0
        self._bad_ranges.clear()
        self._dashboard_nuts.clear()
        self._last_stage_geometry = None
        self._pending_post1 = None
        if drain_queues:
            for q in (self._merged_queue, self._sensor1_queue, self._sensor2_queue):
                while True:
                    try:
                        q.get_nowait()
                        q.task_done()
                    except asyncio.QueueEmpty:
                        break


SENSOR_STATE = SensorState()


def get_sensor_state() -> SensorState:
    return SENSOR_STATE


SensorStateDep = Annotated[SensorState, Depends(get_sensor_state)]
