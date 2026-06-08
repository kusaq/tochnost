from fastapi import APIRouter

from api.v1.auth.dependencies import CurrentUserDep
from api.v1.camera.dependencies import CameraSnapshotDep
from api.v1.camera.schemas import CameraSnapshotRead

router = APIRouter(prefix="/camera", tags=["Camera"])


@router.get(
    "/rail-label/snapshot",
    response_model=CameraSnapshotRead,
    summary="Снимок камеры маркировки рельс",
    description="Возвращает последний кэшированный кадр с камеры FRONT и признак движения.",
)
async def get_rail_label_snapshot(
    user: CurrentUserDep,
    snapshot: CameraSnapshotDep,
) -> CameraSnapshotRead:
    return snapshot
