from fastapi import Query
from pydantic import BaseModel


class PaginationParams(BaseModel):
    limit: int | None = Query(None, ge=1, le=100, description="Количество элементов на странице")
    offset: int | None = Query(None, ge=0, description="Смещение от начала списка")
