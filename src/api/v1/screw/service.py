from typing import Sequence

from fastapi import status
from fastapi.exceptions import HTTPException

from api.v1.base.service import BaseService
from api.v1.screw.schemas import ScrewRead, ScrewDetail, Sensor2Snapshot, ScrewWithLastSensor
from infra.timescale_db.models import Screw
from api.v1.error.schemas import ErrorRead


class ScrewService(BaseService):
    async def list_by_rail(self, rail_id: int) -> Sequence[Screw]:
        return await self.uow.screw.list_by_rail(rail_id=rail_id)

    async def get_detail(self, screw_id: int) -> ScrewDetail | None:
        screw = await self.uow.screw.get_by_id(screw_id)
        if not screw:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screw not found")
        all_s2 = await self.uow.sensor2.list_by_screw(screw_id)
        errors = await self.uow.error.list_by_screw(screw_id)
        # канал гайки: позиции в батчах 1..4, затем повторяются
        ch = ((screw.serial_id - 1) % 4) + 1
        snapshots: list[Sensor2Snapshot] = []
        for s2 in all_s2:
            snapshots.append(
                Sensor2Snapshot(
                    timestamp=s2.timestamp,
                    resistance=s2.resistance,
                    temperature=s2.temperature,
                    humidity=s2.humidity,
                    frequency_status=getattr(s2, f"frequency_status_{ch}"),
                    frequency_torque=getattr(s2, f"frequency_torque_{ch}"),
                    converter_frequency=getattr(s2, f"converter_frequency_{ch}"),
                )
            )
        return ScrewDetail(
            screw=ScrewRead.model_validate(screw, from_attributes=True),
            sensor2=snapshots,
            errors=[ErrorRead.model_validate(e, from_attributes=True) for e in errors],
        )

    async def list_with_last_sensor2_by_rail(self, rail_id: int) -> list[ScrewWithLastSensor]:
        screws = await self.uow.screw.list_by_rail(rail_id=rail_id)
        result: list[ScrewWithLastSensor] = []
        for screw in screws:
            last = await self.uow.sensor2.get_last_by_screw(screw.screw_id)
            snapshot: Sensor2Snapshot | None = None
            if last:
                ch = ((screw.serial_id - 1) % 4) + 1
                snapshot = Sensor2Snapshot(
                    timestamp=last.timestamp,
                    resistance=last.resistance,
                    temperature=last.temperature,
                    humidity=last.humidity,
                    frequency_status=getattr(last, f"frequency_status_{ch}"),
                    frequency_torque=getattr(last, f"frequency_torque_{ch}"),
                    converter_frequency=getattr(last, f"converter_frequency_{ch}"),
                )
            result.append(
                ScrewWithLastSensor(
                    screw=ScrewRead.model_validate(screw, from_attributes=True),
                    last_sensor2=snapshot,
                )
            )
        return result
