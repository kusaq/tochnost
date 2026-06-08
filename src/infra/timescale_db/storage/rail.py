from typing import Sequence

from sqlalchemy import select, func, update

from infra.timescale_db.models import Rail, RailStatus
from infra.timescale_db.storage.base_storage import PostgresStorage
from datetime import datetime, timezone


class RailStorage(PostgresStorage[Rail]):
    model_cls = Rail

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _active_filter():
        return Rail.deleted_at.is_(None)

    async def get_by_id(self, rail_id: int, *, include_deleted: bool = False) -> Rail | None:
        rail = await self._db.get(Rail, rail_id)
        if rail is None:
            return None
        if not include_deleted and rail.deleted_at is not None:
            return None
        return rail

    async def get_by_name(self, name: str) -> Rail | None:
        stmt = select(Rail).where(Rail.name == name, self._active_filter())
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
        stmt = select(Rail).where(self._active_filter())
        count_stmt = select(func.count()).select_from(Rail).where(self._active_filter())
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
            .where(Rail.rail_id == rail_id, self._active_filter())
            .values(**fields)
            .returning(Rail)
        )
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()

    async def delete_by_id(self, rail_id: int) -> int | None:
        """Мягкое удаление: проставляет deleted_at, связанные строки не трогает."""
        stmt = (
            update(Rail)
            .where(Rail.rail_id == rail_id, self._active_filter())
            .values(deleted_at=self._utc_now_naive())
            .returning(Rail.rail_id)
        )
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()

    async def delete_by_ids(self, rail_ids: list[int]) -> list[int]:
        if not rail_ids:
            return []
        stmt = (
            update(Rail)
            .where(Rail.rail_id.in_(rail_ids), self._active_filter())
            .values(deleted_at=self._utc_now_naive())
            .returning(Rail.rail_id)
        )
        res = await self._db.execute(stmt)
        return list(res.scalars().all())

    async def list_in_progress(self) -> Sequence[Rail]:
        stmt = (
            select(Rail)
            .where(Rail.status == RailStatus.IN_PROGRESS, self._active_filter())
            .order_by(Rail.start_time.desc())
        )
        res = await self._db.execute(stmt)
        return res.scalars().all()

    async def count_completed_since(self, since: datetime) -> int:
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
            .where(self._active_filter())
        )
        res = await self._db.execute(stmt)
        return int(res.scalar_one() or 0)
