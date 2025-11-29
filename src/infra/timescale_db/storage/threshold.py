from typing import Sequence

from sqlalchemy import select
from infra.timescale_db.models import Threshold
from infra.timescale_db.storage.base_storage import PostgresStorage


class ThresholdStorage(PostgresStorage[Threshold]):
    model_cls = Threshold

    async def get_by_value(self, value: str) -> Threshold | None:
        stmt = select(Threshold).where(Threshold.value == value)
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_all(self) -> Sequence[Threshold]:
        stmt = select(Threshold).order_by(Threshold.threshold_id.asc())
        res = await self._db.execute(stmt)
        return res.scalars().all()
