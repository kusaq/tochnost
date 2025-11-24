from typing import Sequence

from sqlalchemy import select

from infra.timescale_db.models import Sensor2
from infra.timescale_db.storage.base_storage import PostgresStorage


class Sensor2Storage(PostgresStorage[Sensor2]):
    model_cls = Sensor2

    async def list_by_rail(self, rail_id: int, limit: int = 100, offset: int = 0) -> Sequence[Sensor2]:
        stmt = (
            select(Sensor2)
            .where(Sensor2.rail_id == rail_id)
            .order_by(Sensor2.sensor2_id.asc())
            .offset(offset)
            .limit(limit)
        )
        res = await self._db.execute(stmt)
        return res.scalars().all()


