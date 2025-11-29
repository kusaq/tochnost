from fastapi import HTTPException, status

from api.v1.base.service import BaseService
from api.v1.rail.schemas import RailsListResponse, RailUpdate, RailRead


class RailService(BaseService):
    async def list_rails(
        self,
        *,
        name: str | None,
        status: str | None,
        fastening_type: str | None,
        object_name: str | None,
        limit: int,
        offset: int,
        sort_by: str | None = None,
        order: str | None = None,
    ) -> RailsListResponse:
        items, total = await self.uow.rail.list_filtered_paginated(
            name=name,
            status=status,
            fastening_type=fastening_type,
            object_name=object_name,
            limit=limit,
            offset=offset,
            sort_by=(sort_by or "rail_id"),
            order_desc=(order or "desc").lower() != "asc",
        )
        return RailsListResponse(items=[RailRead.model_validate(i) for i in items], total=total)

    async def update_rail(self, rail_id: int, payload: RailUpdate) -> RailRead | None:
        updated = await self.uow.rail.update_fields(rail_id, **payload.model_dump(exclude_unset=True))
        return RailRead.model_validate(updated) if updated else None

    async def delete_rail(self, rail_id: int) -> None:
        deleted_id = await self.uow.rail.delete_by_id(rail_id)
        if deleted_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rail not found")

    async def delete_rails(self, rail_ids: list[int]) -> int:
        deleted_ids = await self.uow.rail.delete_by_ids(rail_ids)
        if not deleted_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rails not found")
        return len(deleted_ids)


