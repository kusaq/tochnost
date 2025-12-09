from api.v1.auth.router import router as auth_router
from api.v1.sensor.router import router as sensor_router
from api.v1.rail.router import router as rail_router
from api.v1.error.router import router as error_router

__all__ = [
    "auth_router",
    "sensor_router",
    "rail_router",
    "error_router",
]