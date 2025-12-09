from sqlalchemy import select, desc

from infra.timescale_db.models import Sensor2
from infra.timescale_db.storage.base_storage import PostgresStorage


class Sensor2Storage(PostgresStorage[Sensor2]):
    model_cls = Sensor2

    async def get_last_by_screw(self, screw_id: int) -> Sensor2 | None:
        stmt = (
            select(Sensor2)
            .where(Sensor2.screw_id == screw_id)
            .order_by(desc(Sensor2.timestamp))
            .limit(1)
        )
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_screw(self, screw_id: int) -> list[Sensor2]:
        stmt = (
            select(Sensor2)
            .where(Sensor2.screw_id == screw_id)
            .order_by(Sensor2.timestamp.asc())
        )
        res = await self._db.execute(stmt)
        return list(res.scalars().all())
