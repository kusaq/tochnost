from typing import Annotated

from fastapi import Depends

from api.v1.camera.schemas import CameraSnapshotRead
from api.v1.camera.service import get_snapshot


def get_camera_snapshot() -> CameraSnapshotRead:
    return get_snapshot()


CameraSnapshotDep = Annotated[CameraSnapshotRead, Depends(get_camera_snapshot)]
