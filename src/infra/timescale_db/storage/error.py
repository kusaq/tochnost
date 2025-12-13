from typing import Sequence

from sqlalchemy import select, update

from infra.timescale_db.models import Error
from infra.timescale_db.storage.base_storage import PostgresStorage
from sqlalchemy import func


class ErrorStorage(PostgresStorage[Error]):
    model_cls = Error

    async def list_by_rail(self, rail_id: int, is_fixed: bool | None = None) -> Sequence[Error]:
        stmt = select(Error).where(Error.rail_id == rail_id)
        if is_fixed is not None:
            stmt = stmt.where(Error.is_fixed == is_fixed)
        res = await self._db.execute(stmt.order_by(Error.error_id.desc()))
        return res.scalars().all()

    async def update(self, error_id: int, **fields) -> Error | None:
        stmt = (
            update(self.model_cls)
            .where(self.model_cls.error_id == error_id)
            .values(**fields)
            .returning(self.model_cls)
        )
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_screw(self, screw_id: int) -> Sequence[Error]:
        stmt = select(Error).where(Error.screw_id == screw_id).order_by(Error.error_id.desc())
        res = await self._db.execute(stmt)
        return res.scalars().all()

    async def count_all(self) -> int:
        res = await self._db.execute(select(func.count()).select_from(Error))
        return int(res.scalar_one() or 0)
