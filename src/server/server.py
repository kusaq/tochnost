from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from api.v1.sensor.service import start_sensor_workers, stop_sensor_workers
from core.config import settings
from core.logging_config import setup_logging
from server.middlewares.auth import SlidingSessionMiddleware


def _init_router(_app: FastAPI) -> None:
    from api import metrics_router, v1_router

    _app.include_router(v1_router)
    _app.include_router(metrics_router)


def _init_middleware(_app: FastAPI) -> None:
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    _app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
    _app.add_middleware(SlidingSessionMiddleware)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging(
        log_to_file=False if settings.DEBUG else True,
    )
    # start background workers for sensor ingestion
    _app.state.sensor_workers = await start_sensor_workers()
    yield
    # stop background workers
    await stop_sensor_workers()


def create_app() -> FastAPI:
    _app = FastAPI(
        title="Tochnost",
        description="API for Tochnost",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
    )
    _init_router(_app)
    _init_middleware(_app)
    return _app


app = create_app()
