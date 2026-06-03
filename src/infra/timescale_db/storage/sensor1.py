from typing import Sequence

from sqlalchemy import select

from infra.timescale_db.models import Sensor1
from infra.timescale_db.storage.base_storage import PostgresStorage


class Sensor1Storage(PostgresStorage[Sensor1]):
    model_cls = Sensor1

    async def list_by_rail(self, rail_id: int, limit: int = 100, offset: int = 0) -> Sequence[Sensor1]:
        stmt = (
            select(Sensor1)
            .where(Sensor1.rail_id == rail_id)
            .order_by(Sensor1.sensor1_id.asc())
            .offset(offset)
            .limit(limit)
        )
        res = await self._db.execute(stmt)
        return res.scalars().all()

    async def last_by_rail(self, rail_id: int) -> Sensor1 | None:
        stmt = (
            select(Sensor1)
            .where(Sensor1.rail_id == rail_id)
            .order_by(Sensor1.timestamp.desc())
            .limit(1)
        )
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()


