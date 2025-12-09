from sqlalchemy import update
from typing import Sequence
from sqlalchemy import select

from infra.timescale_db.models import Screw
from infra.timescale_db.storage.base_storage import PostgresStorage


class ScrewStorage(PostgresStorage[Screw]):
    model_cls = Screw

    async def update(self, screw_id: int, **fields) -> Screw | None:
        stmt = (
            update(self.model_cls)
            .where(self.model_cls.screw_id == screw_id)
            .values(**fields)
            .returning(self.model_cls)
        )
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_rail(self, rail_id: int) -> Sequence[Screw]:
        stmt = select(Screw).where(Screw.rail_id == rail_id).order_by(Screw.serial_id.asc())
        res = await self._db.execute(stmt)
        return res.scalars().all()
