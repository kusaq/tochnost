from fastapi import APIRouter, Query

from api.v1.auth.dependencies import CurrentUserDep
from api.v1.error.dependencies import ErrorServiceDep
from api.v1.error.schemas import ErrorRead, ErrorFixUpdate


router = APIRouter(tags=["Error"])


@router.get("/rail/{rail_id}/errors", response_model=list[ErrorRead])
async def list_errors(
    rail_id: int,
    is_fixed: bool | None = Query(default=None, description="Фильтр по признаку исправлено"),
    service: ErrorServiceDep = None,
    user: CurrentUserDep = None,
):
    return await service.list_by_rail(rail_id=rail_id, is_fixed=is_fixed)


@router.patch("/error/{error_id}", response_model=ErrorRead)
async def set_error_fixed(
    error_id: int,
    payload: ErrorFixUpdate,
    service: ErrorServiceDep,
    user: CurrentUserDep,
):
    return await service.set_fixed(error_id=error_id, is_fixed=payload.is_fixed)


@router.delete("/error/{error_id}", response_model=dict)
async def delete_error(
    error_id: int,
    service: ErrorServiceDep,
    user: CurrentUserDep,
):
    await service.delete(error_id=error_id)
    return {"deleted": 1}
