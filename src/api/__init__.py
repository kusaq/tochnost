from fastapi import APIRouter

from api.metrics import router as metrics_router
from api.v1 import auth_router, sensor_router


v1_router = APIRouter(prefix="/api/v1", tags=["v1"])
v1_router.include_router(auth_router)
v1_router.include_router(sensor_router)

__all__ = [
    "v1_router",
    "metrics_router",
]
