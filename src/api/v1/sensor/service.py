from collections import deque
from datetime import datetime
from typing import Deque

from api.v1.sensor.schemas import ThresholdEntry, Thresholds, RailSession, Screw as ScrewDC
from api.v1.base.service import BaseService
from api.v1.sensor.schemas import Sensor1Create, Sensor2Create
from infra.timescale_db.models import Rail, Sensor1, Sensor2, Screw
from infra.timescale_db.models.rail import RailStatus
from infra.timescale_db.models.screw import ScrewStatus


class SensorService(BaseService):
    _active: RailSession | None = None

    _closed_keep_limit = 10
    _closed: Deque[RailSession] = deque(maxlen=_closed_keep_limit)

    _total_screws: int = 0
    _screw_session: Deque[ScrewDC] | None = None

    THRESHOLDS_CACHE_KEY = "thresholds:all"

    async def get_threshold_data(self) -> Thresholds:
        cached = await self.redis.get(self.THRESHOLDS_CACHE_KEY)
        if cached:
            return Thresholds.model_validate_json(cached)

        items = await self.uow.threshold.list_all()
        thresholds_dict: dict[str, ThresholdEntry] = {
            t.value: ThresholdEntry(
                min_value=t.min_value,
                max_value=t.max_value,
                is_critical=t.is_critical,
            )
            for t in items
        }
        thresholds_model = Thresholds(thresholds=thresholds_dict)
        await self.redis.set(self.THRESHOLDS_CACHE_KEY, thresholds_model.model_dump_json(), expire=300)
        return thresholds_model

    async def add_sensor2_data(self, sensor2_data: Sensor2Create) -> None:
        if SensorService._active is None:
            if SensorService._screw_session is not None:
                if len(SensorService._closed) > 0:
                    await self.uow.rail.update_fields(
                        rail_id=SensorService._closed[-1].rail_id,
                        sleepers=SensorService._total_screws // 2
                    )
                SensorService._total_screws = 0
                SensorService._screw_session = None
            return

        if SensorService._screw_session is None:
            SensorService._total_screws = 0
            SensorService._screw_session = deque()

        if all([
            sensor2_data.values.frequency_torque_1==0,
            sensor2_data.values.frequency_torque_2==0,
            sensor2_data.values.frequency_torque_3==0,
            sensor2_data.values.frequency_torque_4==0,
        ]):
            if len(SensorService._screw_session) > 0:
                threshold = await self.get_threshold_data()

                for num, screw in enumerate(SensorService._screw_session):
                    status = ScrewStatus.COMPLETED
                    if threshold.thresholds["frequency_torque"].min_value < screw.frequency_torque < threshold.thresholds["frequency_torque"].max_value:
                        status = ScrewStatus.COMPLETED_WITH_ERROR
                    await self.uow.screw.update(
                        screw_id=screw.screw_id,
                        status=status
                    )
                SensorService._screw_session = deque()
            return

        sensors = []
        for i in range(1, 5):
            if len(SensorService._screw_session) < i:
                screw_id = await self.add_screw(
                    getattr(sensor2_data.values, f"frequency_torque_{i}"),
                    sensor2_data.timestamp,
                )
            else:
                screw_id = SensorService._screw_session[i-1].screw_id
            sensors.append(
                Sensor2(timestamp=sensor2_data.timestamp, screw_id=screw_id, **sensor2_data.values.model_dump())
            )
        await self.uow.sensor2.add_many(sensors)

    async def add_screw(self, frequency_torque: int, ts: datetime) -> int:
        serial_number = SensorService._total_screws + 1
        SensorService._total_screws += 1
        screw = await self.uow.screw.add(Screw(rail_id=SensorService._active.rail_id, serial_id=serial_number))
        SensorService._screw_session.append(
            ScrewDC(
                screw_id=screw.screw_id,
                timestamp=ts,
                frequency_torque=frequency_torque,
            )
        )
        return screw.screw_id

    async def add_sensor1_data(self, data: Sensor1Create) -> None:
        rail_id = self.is_in_closed(data.timestamp)
        if rail_id is not None:
            await self.uow.sensor1.add(
                Sensor1(rail_id=rail_id, timestamp=data.timestamp, **data.values.model_dump())
            )
            return

        if SensorService._active:
            if data.timestamp < SensorService._active.start_time:
                return

            if data.values.mm_along_rail >= SensorService._active.last_mm_along_rail:
                SensorService._active.last_mm_along_rail = data.values.mm_along_rail
                SensorService._active.last_timestamp = data.timestamp
                await self.uow.sensor1.add(
                    Sensor1(
                        rail_id=SensorService._active.rail_id,
                        timestamp=data.timestamp,
                        **data.values.model_dump(),
                    )
                )
            elif data.values.mm_along_rail == 0:
                await self.close_active_rail()
            return

        if data.values.mm_along_rail > 0:
            await self.bind_active_rail(data)
        return

    async def close_active_rail(self) -> None:
        completed_rail = await self.uow.rail.update_fields(
            status=RailStatus.COMPLETED,
            rail_id=SensorService._active.rail_id,
            end_time=SensorService._active.last_timestamp
        )
        SensorService._active.end_time = completed_rail.end_time
        SensorService._closed.append(SensorService._active)
        SensorService._active = None

    async def bind_active_rail(self, data: Sensor1Create) -> None:
        rail = await self.uow.rail.add(Rail(start_time=data.timestamp))
        SensorService._active = RailSession(
            rail_id=rail.rail_id,
            start_time=data.timestamp,
            end_time=None,
            last_mm_along_rail=data.values.mm_along_rail,
            last_timestamp=data.timestamp,
        )
        await self.uow.sensor1.add(
            Sensor1(rail_id=rail.rail_id, timestamp=data.timestamp, **data.values.model_dump())
        )

    @classmethod
    def is_in_closed(cls, ts: datetime) -> int | None:
        """
        Проверяет, входит ли ts в какой-то из интервалов.
        """
        for session in reversed(cls._closed):
            if ts < session.start_time:
                continue
            if ts <= session.end_time:
                return session.rail_id
            if ts > session.end_time:
                break
        return None
