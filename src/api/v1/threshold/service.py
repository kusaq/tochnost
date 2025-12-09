from typing import Sequence

from api.v1.base.service import BaseService
from fastapi import HTTPException, status
from infra.timescale_db.models import Threshold


class ThresholdService(BaseService):
    async def list_all(self) -> Sequence[Threshold]:
        return await self.uow.threshold.list_all()

    async def get_by_value(self, value: str) -> Threshold:
        obj = await self.uow.threshold.get_by_value(value)
        if not obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Threshold not found")
        return obj

    async def get_by_id(self, threshold_id: int) -> Threshold:
        obj = await self.uow.threshold.get_by_id(threshold_id)
        if not obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Threshold not found")
        return obj
