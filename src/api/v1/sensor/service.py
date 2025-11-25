from datetime import timezone

from api.v1.base.service import BaseService
from api.v1.sensor.schemas import Sensor2Create
from infra.timescale_db.models import Sensor2


class SensorService(BaseService):
    async def add_sensor2_data(self, sensor2_data: Sensor2Create) -> None:
        dt = sensor2_data.timestamp
        if getattr(dt, "tzinfo", None) is not None and dt.utcoffset() is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        sensor_data = Sensor2(
            timestamp=dt,
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
        await self.uow.sensor2.add(sensor_data)

