from fastapi import APIRouter

from api.v1.auth.dependencies import CurrentUserDep
from api.v1.threshold.dependencies import ThresholdServiceDep
from api.v1.threshold.schemas import ThresholdRead


router = APIRouter(prefix="/threshold", tags=["Threshold"])


@router.get(
    "",
    response_model=list[ThresholdRead],
    summary="Список порогов или поиск по названию",
    description="Возвращает все пороги. Если передан параметр ?value=, возвращает список с найденным порогом.",
    responses={
        404: {"description": "Порог не найден (если указан value и порог отсутствует)"},
    },
)
async def list_thresholds(
    service: ThresholdServiceDep,
    user: CurrentUserDep,
    value: str | None = None,
):
    if value:
        obj = await service.get_by_value(value)
        return [obj]
    return await service.list_all()


@router.get(
    "/{threshold_id}",
    response_model=ThresholdRead,
    summary="Порог по идентификатору",
    description="Возвращает порог по его идентификатору.",
    responses={
        404: {"description": "Порог не найден"},
    },
)
async def get_threshold_by_id(
    threshold_id: int,
    service: ThresholdServiceDep,
    user: CurrentUserDep,
):
    return await service.get_by_id(threshold_id)
