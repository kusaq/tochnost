from typing import Sequence

from sqlalchemy import select, func, update, delete

from infra.timescale_db.models import Rail, RailStatus
from infra.timescale_db.storage.base_storage import PostgresStorage
from datetime import datetime, timezone


class RailStorage(PostgresStorage[Rail]):
    model_cls = Rail

    async def get_by_name(self, name: str) -> Rail | None:
        stmt = select(Rail).where(Rail.name == name)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_filtered_paginated(
        self,
        *,
        name: str | None = None,
        status: str | None = None,
        fastening_type: str | None = None,
        object_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "rail_id",
        order_desc: bool = True,
    ) -> tuple[Sequence[Rail], int]:
        stmt = select(Rail)
        count_stmt = select(func.count()).select_from(Rail)
        if name:
            like = f"%{name}%"
            stmt = stmt.where(Rail.name.ilike(like))
            count_stmt = count_stmt.where(Rail.name.ilike(like))
        if status:
            stmt = stmt.where(Rail.status == status)
            count_stmt = count_stmt.where(Rail.status == status)
        if fastening_type:
            stmt = stmt.where(Rail.fastening_type == fastening_type)
            count_stmt = count_stmt.where(Rail.fastening_type == fastening_type)
        if object_name:
            stmt = stmt.where(Rail.object_name == object_name)
            count_stmt = count_stmt.where(Rail.object_name == object_name)
        # Безопасный выбор поля сортировки
        sort_map = {
            "rail_id": Rail.rail_id,
            "start_time": Rail.start_time,
            "end_time": Rail.end_time,
        }
        sort_col = sort_map.get(sort_by, Rail.rail_id)
        stmt = stmt.order_by(sort_col.desc() if order_desc else sort_col.asc()).offset(offset).limit(limit)
        res = await self._db.execute(stmt)
        items = res.scalars().all()
        total_res = await self._db.execute(count_stmt)
        total = int(total_res.scalar_one())
        return items, total

    async def update_fields(self, rail_id: int, **fields) -> Rail | None:
        stmt = (
            update(Rail)
            .where(Rail.rail_id == rail_id)
            .values(**fields)
            .returning(Rail)
        )
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()

    async def delete_by_id(self, rail_id: int) -> int | None:
        stmt = delete(Rail).where(Rail.rail_id == rail_id).returning(Rail.rail_id)
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()

    async def delete_by_ids(self, rail_ids: list[int]) -> list[int]:
        if not rail_ids:
            return []
        stmt = delete(Rail).where(Rail.rail_id.in_(rail_ids)).returning(Rail.rail_id)
        res = await self._db.execute(stmt)
        deleted = res.scalars().all()
        return list(deleted)

    async def count_completed_since(self, since: datetime) -> int:
        """
        Кол-во завершённых рельс с конца since (по end_time).
        """
        # Приводим к наивному UTC, так как колонка end_time = TIMESTAMP WITHOUT TIME ZONE
        since_param = since
        if since.tzinfo is not None:
            try:
                since_param = since.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                since_param = since.replace(tzinfo=None)
        stmt = (
            select(func.count())
            .select_from(Rail)
            .where(Rail.status == RailStatus.COMPLETED)
            .where(Rail.end_time.is_not(None))
            .where(Rail.end_time >= since_param)
        )
        res = await self._db.execute(stmt)
        return int(res.scalar_one() or 0)
