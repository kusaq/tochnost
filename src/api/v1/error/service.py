from typing import Sequence

from fastapi import HTTPException, status

from api.v1.base.service import BaseService
from infra.timescale_db.models import Error


class ErrorService(BaseService):
    async def list_by_rail(self, rail_id: int, is_fixed: bool | None) -> Sequence[Error]:
        items = await self.uow.error.list_by_rail(rail_id=rail_id, is_fixed=is_fixed)
        return items

    async def set_fixed(self, error_id: int, is_fixed: bool) -> Error:
        updated = await self.uow.error.update(error_id=error_id, is_fixed=is_fixed)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Error not found")
        return updated

    async def delete(self, error_id: int) -> None:
        obj = await self.uow.error.get_by_id(error_id)
        if not obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Error not found")
        await self.uow.error.delete(obj)
