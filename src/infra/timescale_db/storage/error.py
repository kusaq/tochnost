from typing import Sequence

from sqlalchemy import select, update, func

from infra.timescale_db.models import Error
from infra.timescale_db.storage.base_storage import PostgresStorage
from datetime import datetime, timezone


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

    async def count_grouped_by_hour_since(self, since: datetime) -> list[tuple[datetime, int]]:
        """
        Возвращает список (час, количество) для ошибок, созданных с момента 'since' включительно.
        Час усечён до начала часа (date_trunc('hour', created_at)).
        """
        # TIMESTAMP WITHOUT TIME ZONE: приводим к наивному UTC
        since_param = since
        if since.tzinfo is not None:
            try:
                since_param = since.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                since_param = since.replace(tzinfo=None)
        bucket = func.date_trunc("hour", Error.created_at).label("hour_bucket")
        stmt = (
            select(bucket, func.count().label("cnt"))
            .where(Error.created_at >= since_param)
            .group_by(bucket)
            .order_by(bucket.asc())
        )
        res = await self._db.execute(stmt)
        rows = res.all()
        return [(row.hour_bucket, int(row.cnt)) for row in rows]

    async def count_by_rail(self, rail_id: int, is_fixed: bool | None = None) -> int:
        """
        Количество ошибок по конкретной рельсе.
        """
        stmt = select(func.count()).select_from(Error).where(Error.rail_id == rail_id)
        if is_fixed is not None:
            stmt = stmt.where(Error.is_fixed == is_fixed)
        res = await self._db.execute(stmt)
        return int(res.scalar_one() or 0)
