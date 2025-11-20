from typing import Annotated
from fastapi import Query, Depends

from api.v1.base.schemas import PaginationParams


def pagination_params(
    limit: int | None = Query(20, ge=1, le=100),
    offset: int | None = Query(None, ge=0),
) -> PaginationParams:
    return PaginationParams(limit=limit, offset=offset)


PaginationDep = Annotated[PaginationParams, Depends(pagination_params)]
