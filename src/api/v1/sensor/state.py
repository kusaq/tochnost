from collections import deque
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
        # generic bad ranges by metric key: key -> (start_mm, start_value)
        self._bad_ranges: dict[str, tuple[int, float]] = {}

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

    def update_screw_max_torque(self, index: int, new_value: int) -> None:
        current = self._screw_session[index].frequency_torque
        self._screw_session[index].frequency_torque = max(current, new_value)

    def iter_screws(self):
        return iter(self._screw_session)

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
