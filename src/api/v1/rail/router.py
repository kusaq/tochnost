from typing import Literal

from fastapi import APIRouter, Query

from api.v1.base.dependencies import PaginationDep
from api.v1.rail.dependencies import RailServiceDep
from api.v1.rail.schemas import RailsListResponse, RailUpdate, RailRead
from api.v1.auth.dependencies import CurrentUserDep


router = APIRouter(prefix="/rail", tags=["Rail"])


@router.get("", response_model=RailsListResponse)
async def list_rails(
    service: RailServiceDep,
    pagination: PaginationDep,
    user: CurrentUserDep,
    name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    fastening_type: str | None = Query(default=None),
    object_name: str | None = Query(default=None),
    sort_by: Literal["rail_id", "start_time", "end_time"] = Query(default="rail_id"),
    order: Literal["asc", "desc"] = Query(default="desc"),
):
    return await service.list_rails(
        name=name,
        status=status,
        fastening_type=fastening_type,
        object_name=object_name,
        limit=pagination.limit or 20,
        offset=pagination.offset or 0,
        sort_by=sort_by,
        order=order,
    )


@router.patch("/{rail_id}", response_model=RailRead | None)
async def update_rail(
    rail_id: int,
    payload: RailUpdate,
    service: RailServiceDep,
    user: CurrentUserDep,
):
    return await service.update_rail(rail_id, payload)


@router.delete("", response_model=dict)
async def delete_rails(
    rail_ids: list[int],
    service: RailServiceDep,
    user: CurrentUserDep,
):
    deleted = await service.delete_rails(rail_ids)
    return {"deleted": deleted}


@router.delete("/{rail_id}", response_model=dict)
async def delete_rail(
    rail_id: int,
    service: RailServiceDep,
    user: CurrentUserDep,
):
    await service.delete_rail(rail_id)
    return {"deleted": 1}
