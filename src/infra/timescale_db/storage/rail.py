from sqlalchemy import select

from infra.timescale_db.models import Rail
from infra.timescale_db.storage.base_storage import PostgresStorage


class RailStorage(PostgresStorage[Rail]):
    model_cls = Rail

    async def get_by_name(self, name: str) -> Rail | None:
        stmt = select(Rail).where(Rail.name == name)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()


