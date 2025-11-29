from api.v1.base.service import BaseService
from api.v1.sensor.manager import SensorManager
from api.v1.sensor.schemas import Sensor1Create, Sensor2Create
from infra.timescale_db.models import Rail, Sensor1, Sensor2
from infra.timescale_db.models.rail import RailStatus


class SensorService(BaseService):
    async def add_sensor1_data(self, sensor1_data: Sensor1Create, manager: SensorManager) -> None:
        rail_id, event = await manager.assign_rail_for_sensor1(sensor1_data)

        if event and event.get("type") == "start":
            rail = Rail(
                name=None,
                status=RailStatus.IN_PROGRESS,
                object_name=None,
                fastening_type=None,
                sleepers=None,
                start_time=event["start_time"],
                end_time=None,
            )
            rail = await self.uow.rail.add(rail)
            await manager.bind_active_rail(rail.rail_id)
            rail_id = rail.rail_id
        elif event and event.get("type") == "close" and rail_id is not None:
            rail = await self.uow.rail.get_by_id(rail_id)
            if rail:
                rail.end_time = event["end_time"]
                rail.status = RailStatus.COMPLETED
                await self.uow.rail.update(rail)
                return

        if rail_id is None:
            return

        await self.uow.sensor1.add(
            Sensor1(
                encoder1=sensor1_data.values.encoder1,
                encoder2=sensor1_data.values.encoder2,
                encoder3=sensor1_data.values.encoder3,
                encoder4=sensor1_data.values.encoder4,
                mm_along_rail=sensor1_data.values.mm_along_rail,
                laser_on_rail_left=sensor1_data.values.laser_on_rail_left,
                laser_on_rail_right=sensor1_data.values.laser_on_rail_right,
                laser_on_tie_left=sensor1_data.values.laser_on_tie_left,
                laser_on_tie_right=sensor1_data.values.laser_on_tie_right,
                mm_gauge=sensor1_data.values.mm_gauge,
                mm_side_wear_left=sensor1_data.values.mm_side_wear_left,
                mm_side_wear_right=sensor1_data.values.mm_side_wear_right,
                mm_vertical_wear_left=sensor1_data.values.mm_vertical_wear_left,
                mm_vertical_wear_right=sensor1_data.values.mm_vertical_wear_right,
                rad_rail_tilt_left=sensor1_data.values.rad_rail_tilt_left,
                rad_rail_tilt_right=sensor1_data.values.rad_rail_tilt_right,
                mm_bolt_height_left_inner=sensor1_data.values.mm_bolt_height_left_inner,
                mm_bolt_height_left_outer=sensor1_data.values.mm_bolt_height_left_outer,
                mm_bolt_height_right_inner=sensor1_data.values.mm_bolt_height_right_inner,
                mm_bolt_height_right_outer=sensor1_data.values.mm_bolt_height_right_outer,
                timestamp=sensor1_data.timestamp,
                rail_id=rail_id,
            )
        )

    async def add_sensor2_data(self, sensor2_data: Sensor2Create) -> None:
        await self.uow.sensor2.add(
            Sensor2(
            timestamp=sensor2_data.timestamp,
            resistance_1=sensor2_data.values.resistance_1,
            resistance_2=sensor2_data.values.resistance_2,
            moment_pc=sensor2_data.values.moment_pc,
            moment_percent=sensor2_data.values.moment_percent,
            moment_amperage_percent=sensor2_data.values.moment_amperage_percent,
            turnover=sensor2_data.values.turnover,
            amperage=sensor2_data.values.amperage,
            phase_amperage=sensor2_data.values.phase_amperage,
            revolutions_pc_alt=sensor2_data.values.revolutions_pc_alt,
            status_pc=sensor2_data.values.status_pc,
        )
        )
