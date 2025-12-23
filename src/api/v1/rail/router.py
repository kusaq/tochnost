from typing import Literal
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from api.v1.base.dependencies import PaginationDep
from api.v1.rail.dependencies import RailServiceDep
from api.v1.rail.schemas import (
    RailsListResponse,
    RailUpdate,
    RailRead,
    RailMetricRead,
    SensorSeriesRequest,
    RailSensorSeries,
)
from api.v1.auth.dependencies import CurrentUserDep


router = APIRouter(prefix="/rail", tags=["Rail"])


@router.get(
    "",
    response_model=RailsListResponse,
    summary="Список рельс",
    description="Возвращает список рельс с фильтрами, пагинацией и сортировкой.",
)
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


@router.patch(
    "/{rail_id}",
    response_model=RailRead | None,
    summary="Частичное обновление рельсы",
    description="Обновляет поля рельсы по идентификатору.",
)
async def update_rail(
    rail_id: int,
    payload: RailUpdate,
    service: RailServiceDep,
    user: CurrentUserDep,
):
    return await service.update_rail(rail_id, payload)


@router.delete(
    "",
    response_model=dict,
    summary="Массовое удаление рельс",
    description="Удаляет рельсы по списку идентификаторов. Возвращает количество удалённых записей.",
    responses={
        404: {"description": "Рельсы не найдены"},
    },
)
async def delete_rails(
    rail_ids: list[int],
    service: RailServiceDep,
    user: CurrentUserDep,
):
    deleted = await service.delete_rails(rail_ids)
    return {"deleted": deleted}


@router.delete(
    "/{rail_id}",
    response_model=dict,
    summary="Удаление рельсы",
    description="Удаляет рельсу по идентификатору. Возвращает { deleted: 1 } при успехе.",
    responses={
        404: {"description": "Рельса не найдена"},
    },
)
async def delete_rail(
    rail_id: int,
    service: RailServiceDep,
    user: CurrentUserDep,
):
    await service.delete_rail(rail_id)
    return {"deleted": 1}


@router.get(
    "/{rail_id}/metrics",
    response_model=list[RailMetricRead],
    summary="Агрегированные показания по рельсе",
    description="Возвращает список метрик: название, агрегированное значение (или пусто), требуемое значение (если есть), список исходных значений, примечание.",
)
async def get_rail_metrics(
    rail_id: int,
    service: RailServiceDep,
    user: CurrentUserDep,
):
    return await service.get_aggregated_metrics(rail_id)


@router.get(
    "/{rail_id}/export",
    summary="Выгрузка данных рельсы в Excel",
    description="Формирует и возвращает Excel-файл с агрегированными данными по рельсе.",
)
async def export_rail_excel(
    rail_id: int,
    service: RailServiceDep,
    user: CurrentUserDep,
):
    content = await service.export_metrics_excel(rail_id)
    filename = f"rail_{rail_id}_metrics.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/sensors/query",
    response_model=list[RailSensorSeries],
    summary="Сырые данные датчиков по рельсам",
    description=(
        "Принимает список рельс и полей, возвращает по каждой рельсе список точек во времени: "
        "{ rail_id, points: [ { timestamp, values{поле: значение} } ] }."
    ),
)
async def get_sensor_series(
    payload: SensorSeriesRequest,
    service: RailServiceDep,
    user: CurrentUserDep,
):
    return await service.get_sensor_series(payload)
