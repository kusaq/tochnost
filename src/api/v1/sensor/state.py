from collections import deque
import asyncio
from datetime import datetime
from typing import Deque, Annotated

from fastapi import Depends

from api.v1.sensor.schemas import RailSession, Screw as ScrewDC


class SensorState:
    """
    Хранит оперативное состояние датчиков и рельсов между запросами (без доступа к БД).
    """
    def __init__(self, closed_keep_limit: int = 10) -> None:
        self._active: RailSession | None = None
        self._closed: Deque[RailSession] = deque(maxlen=closed_keep_limit)
        self._total_screws: int = 0
        self._screw_session: Deque[ScrewDC] = deque()
        # high-throughput ingestion queues
        self._sensor1_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._sensor2_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        # generic bad ranges by metric key: key -> (start_mm, start_value)
        self._bad_ranges: dict[str, tuple[int, float]] = {}
        # resistance stats
        self._res_sum: float = 0.0
        self._res_count: int = 0
        self._res_current: float = 0.0
        # gauge stats
        self._gauge_sum: float = 0.0
        self._gauge_count: int = 0

    # ---- Active rail helpers ----
    def has_active_rail(self) -> bool:
        return self._active is not None

    def get_active_rail(self) -> RailSession | None:
        return self._active

    def set_active(self, session: RailSession) -> None:
        self._active = session

    def clear_active(self) -> None:
        self._active = None

    def update_active_progress(self, mm_along_rail: int, ts: datetime) -> None:
        if self._active:
            self._active.last_mm_along_rail = mm_along_rail
            self._active.last_timestamp = ts

    # ---- Screws/session helpers ----
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

    # ---- Ingestion queues ----
    def sensor1_queue(self) -> asyncio.Queue:
        return self._sensor1_queue

    def sensor2_queue(self) -> asyncio.Queue:
        return self._sensor2_queue

    # ---- Generic bad range helpers ----
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

    # ---- Total screws helpers ----
    def reset_total_screws(self) -> None:
        self._total_screws = 0

    def next_serial(self) -> int:
        self._total_screws += 1
        return self._total_screws

    def get_total_screws(self) -> int:
        return self._total_screws

    # ---- Resistance stats helpers ----
    def update_resistance(self, value: float) -> None:
        self._res_current = float(value)
        self._res_sum += float(value)
        self._res_count += 1

    def get_resistance_current(self) -> float:
        return float(self._res_current)

    def get_resistance_average(self) -> float:
        if self._res_count == 0:
            return 0.0
        return float(self._res_sum / self._res_count)

    def reset_resistance_stats(self) -> None:
        self._res_sum = 0.0
        self._res_count = 0
        self._res_current = 0.0

    # ---- Gauge (mm_gauge) stats helpers ----
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

    # ---- Sides counts (for active rail) ----
    def reset_laser_counts(self) -> None:
        self._laser_left_true_count = 0
        self._laser_right_true_count = 0

    def record_laser_flags(self, left_on_rail: bool, right_on_rail: bool) -> None:
        """
        Учитывает текущие показания попадания лазера на рельс слева/справа.
        """
        # Инициализация на лету, если не вызывали reset явно
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

    def get_left_right_counts(self) -> tuple[int, int]:
        """
        Возвращает (left_count, right_count) исходя из общего количества гаек:
        В каждом батче из 4: 1 и 2 — левый, 3 и 4 — правый.
        """
        total = self._total_screws
        full_batches = total // 4
        rem = total % 4
        left = full_batches * 2 + min(2, rem)
        right = total - left
        return left, right

    # ---- Closed rails helpers ----
    def closed_len(self) -> int:
        return len(self._closed)

    def last_closed(self) -> RailSession | None:
        return None if len(self._closed) == 0 else self._closed[-1]

    def append_closed(self, session: RailSession) -> None:
        self._closed.append(session)

    def is_in_closed(self, ts: datetime) -> int | None:
        """
        Проверяет, входит ли ts в один из завершённых интервалов.
        """
        for session in reversed(self._closed):
            if ts < session.start_time:
                continue
            end_ts = session.end_time or session.last_timestamp or session.start_time
            if ts <= end_ts:
                return session.rail_id
            if ts > end_ts:
                break
        return None


SENSOR_STATE = SensorState()

def get_sensor_state() -> SensorState:
    return SENSOR_STATE

SensorStateDep = Annotated[SensorState, Depends(get_sensor_state)]
