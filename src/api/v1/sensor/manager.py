import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Deque

from fastapi import Depends

from api.v1.sensor.schemas import Sensor1Create


@dataclass(slots=True)
class RailSession:
    rail_id: int | None
    start_time: datetime
    end_time: datetime | None
    last_mm_along_rail: int
    last_timestamp: datetime


class SensorManager:
    """
    Синглтон для группировки показаний по рельсу.
    Логика:
    - Когда мм вдоль рельса растёт, считаем, что идёт тот же рельс.
    - Если рост прекратился дольше порога, текущий рельс завершается.
    - Запоздавшие показания распределяются по окнам времени уже известных рельс.
    """
    _lock: asyncio.Lock

    # Храним недавние завершённые рельсы для маршрутизации запоздавших показаний
    _closed_keep_limit: int = 100

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active: RailSession | None = None
        self._closed: Deque[RailSession] = deque(maxlen=self._closed_keep_limit)

    def is_in_closed(self, ts: datetime) -> int | None:
        """
        Проверяет, входит ли ts в какой-то из интервалов.
        """
        for session in reversed(self._closed):
            if ts < session.start_time:
                continue
            if ts <= session.end_time:
                return session.rail_id
            if ts > session.end_time:
                break
        return None

    async def assign_rail_for_sensor1(self, data: Sensor1Create) -> tuple[int | None, dict | None]:
        """
        Решает к какому рельсу отнести показание.
        Возвращает:
          - (rail_id, None) если найден активный или закрытый рельс
          - (None, {'type': 'start', 'start_time': ts}) если нужно начать новый рельс
          - (None, None) если нечего делать (нет активного и признаков начала)
          - (rail_id, {'type': 'close', 'end_time': ts}) если во время обработки нужно закрыть текущий
        """
        async with self._lock:
            # Сначала пробуем отнести к уже завершённым окнам (запоздавшие данные)
            rail_id = self.is_in_closed(data.timestamp)
            if rail_id is not None:
                return rail_id, None

            # Есть активный рельс?
            if self._active:
                # Если показание старее начала активного - отнести некуда
                if data.timestamp < self._active.start_time:
                    return None, None

                # Проверяем рост мм
                if data.values.mm_along_rail > self._active.last_mm_along_rail:
                    self._active.last_mm_along_rail = data.values.mm_along_rail
                    self._active.last_timestamp = data.timestamp
                    return self._active.rail_id, None

                # Нет роста — Сигнализируем о необходимости закрыть активный рельс
                end_ts = self._active.last_timestamp
                rail_id = self._active.rail_id
                # Перекладываем в закрытые
                self._active.end_time = end_ts
                self._closed.append(self._active)
                self._active = None
                if rail_id is not None:
                    return rail_id, {"type": "close", "end_time": end_ts}

            # Активного нет — старт нового рельса только если есть признак (mm > 0)
            last_mm_along_rail = None
            if len(self._closed) >= 1:
                last_mm_along_rail = self._closed[-1].last_mm_along_rail

            if data.values.mm_along_rail > (last_mm_along_rail or 0):
                # Создаём пустую сессию и просим сервис инициировать рельс в БД
                self._active = RailSession(
                    rail_id=None,
                    start_time=data.timestamp,
                    end_time=None,
                    last_mm_along_rail=0,
                    last_timestamp=data.timestamp,
                )
                self._active.last_mm_along_rail = data.values.mm_along_rail
                self._active.last_timestamp = data.timestamp
                return None, {"type": "start", "start_time": data.timestamp}

            # Нет активного и нет признаков начала — не сохраняем
            return None, None

    async def bind_active_rail(self, rail_id: int) -> None:
        async with self._lock:
            if self._active and self._active.rail_id is None:
                self._active.rail_id = rail_id


manager = SensorManager()

def get_manager() -> SensorManager:
    return manager

SensorManagerDep = Annotated[SensorManager, Depends(get_manager)]