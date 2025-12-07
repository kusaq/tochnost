from datetime import datetime
import math

from api.v1.sensor.schemas import ThresholdEntry, Thresholds, RailSession, Screw as ScrewDC
from api.v1.base.service import BaseService
from api.v1.sensor.schemas import Sensor1Create, Sensor2Create
from infra.timescale_db.models import Rail, Sensor1, Sensor2, Screw, RailStatus, ScrewStatus
from api.v1.sensor.state import SensorState


class SensorService(BaseService):
    state: SensorState

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
        if not self.state.has_active_rail():
            return
        
        if sensor2_data.values.all_frequency_status_zero():
            if self.state.has_screw_session:
                threshold = await self.get_threshold_data()

                for screw in list(self.state.iter_screws()):
                    status = ScrewStatus.COMPLETED
                    ft_threshold = threshold.thresholds.get("frequency_torque")
                    if ft_threshold:
                        ft_value = screw.frequency_torque
                        if ft_value < ft_threshold.min_value or ft_value > ft_threshold.max_value:
                            status = ScrewStatus.COMPLETED_WITH_ERROR
                    await self.uow.screw.update(screw_id=screw.screw_id, status=status)
                self.state.clear_screw_session()
            return

        sensors = []
        for i in range(1, 5):
            if self.state.screw_session_len < i:
                screw_id = await self.add_screw(
                    getattr(sensor2_data.values, f"frequency_torque_{i}"),
                    sensor2_data.timestamp,
                )
            else:
                screw_id = self.state.screw_session_item(i-1).screw_id
                self.state.update_screw_max_torque(i-1, getattr(sensor2_data.values, f"frequency_torque_{i}"))
            sensors.append(
                Sensor2(timestamp=sensor2_data.timestamp, screw_id=screw_id, **sensor2_data.values.model_dump())
            )
        await self.uow.sensor2.add_many(sensors)

    async def add_screw(self, frequency_torque: int, ts: datetime) -> int:
        serial_number = self.state.next_serial()
        active = self.state.get_active_rail()
        screw = await self.uow.screw.add(Screw(rail_id=active.rail_id, serial_id=serial_number))
        self.state.append_screw(
            ScrewDC(
                screw_id=screw.screw_id,
                timestamp=ts,
                frequency_torque=frequency_torque,
            )
        )
        return screw.screw_id

    async def add_sensor1_data(self, data: Sensor1Create) -> None:
        rail_id = self.state.is_in_closed(data.timestamp)
        if rail_id is not None:
            await self.uow.sensor1.add(
                Sensor1(rail_id=rail_id, timestamp=data.timestamp, **data.values.model_dump())
            )
            return

        active = self.state.get_active_rail()
        if active:
            if data.timestamp < active.start_time:
                return

            if data.values.mm_along_rail >= active.last_mm_along_rail:
                self.state.update_active_progress(data.values.mm_along_rail, data.timestamp)
                await self.uow.sensor1.add(
                    Sensor1(
                        rail_id=active.rail_id,
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
        active = self.state.get_active_rail()
        completed_rail = await self.uow.rail.update_fields(
            rail_id=active.rail_id,
            status=RailStatus.COMPLETED,
            end_time=active.last_timestamp,
            sleepers=math.ceil(self.state.get_total_screws() / 4),
        )
        active.end_time = completed_rail.end_time
        self.state.append_closed(active)
        self.state.clear_active()

    async def bind_active_rail(self, data: Sensor1Create) -> None:
        self.state.reset_total_screws()
        self.state.clear_screw_session()
        rail = await self.uow.rail.add(Rail(start_time=data.timestamp))
        self.state.set_active(RailSession(
            rail_id=rail.rail_id,
            start_time=data.timestamp,
            end_time=None,
            last_mm_along_rail=data.values.mm_along_rail,
            last_timestamp=data.timestamp,
        ))
        await self.uow.sensor1.add(
            Sensor1(rail_id=rail.rail_id, timestamp=data.timestamp, **data.values.model_dump())
        )
