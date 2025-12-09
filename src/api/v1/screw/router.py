from fastapi import APIRouter

from api.v1.auth.dependencies import CurrentUserDep
from api.v1.screw.dependencies import ScrewServiceDep
from api.v1.screw.schemas import ScrewRead, ScrewDetail


router = APIRouter(tags=["Screw"])


@router.get("/screw/{rail_id}", response_model=list[ScrewRead])
async def list_screws(
    rail_id: int,
    service: ScrewServiceDep = None,
    user: CurrentUserDep = None,
):
    return await service.list_by_rail(rail_id=rail_id)


@router.get("/screw/{screw_id}", response_model=ScrewDetail)
async def get_screw(
    screw_id: int,
    service: ScrewServiceDep,
    user: CurrentUserDep,
):
    return await service.get_detail(screw_id)
