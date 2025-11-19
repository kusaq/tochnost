from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import CaptureSession, ModbusReading, RailGrid
from app.schemas import (
    CameraTestRequest,
    CameraTestResult,
    CaptureRequest,
    CaptureResponse,
    ModbusPollStatusResponse,
    ModbusReadRequest,
    ModbusReadResponse,
    ModbusValue,
    RailGridResponse,
    TokenResponse,
)
from app.security import authenticate_user, create_access_token, get_current_user
from app.services.camera_service import capture_with_cameras, test_cameras
from app.services.modbus_service import read_modbus
from app.services.modbus_poller import get_poller

settings = get_settings()

app = FastAPI(title=settings.api_title, version=settings.api_version)


@app.on_event("startup")
async def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    # Start Modbus polling if enabled
    poller = get_poller(settings)
    await poller.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    # Stop Modbus polling
    poller = get_poller(settings)
    await poller.stop()


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/auth/token", response_model=TokenResponse, tags=["auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if not authenticate_user(form_data.username, form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": settings.api_username})
    return TokenResponse(access_token=access_token)


@app.post("/api/v1/capture", response_model=CaptureResponse, tags=["cameras"])
async def start_capture(
    request: CaptureRequest,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Захватывает изображения с камер Hikvision."""
    logger.info(
        f"[API] Запрос на захват изображений: UID={request.uid}, "
        f"connection_class={request.connection_class}"
    )
    
    try:
        result = await run_in_threadpool(capture_with_cameras, request, settings)
        logger.info(
            f"[API] Захват успешно завершен: UID={request.uid}, "
            f"front={result.front_saved}, top={result.top_saved}"
        )
    except ValueError as e:
        error_detail = (
            f"Ошибка конфигурации камер: {str(e)}. "
            f"Проверьте параметры запроса и настройки камер."
        )
        logger.error(f"[API] Ошибка захвата (ValueError): {error_detail}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail
        ) from e
    except RuntimeError as e:
        error_detail = (
            f"Ошибка при захвате изображений: {str(e)}. "
            f"Проверьте доступность камер и настройки."
        )
        logger.error(f"[API] Ошибка захвата (RuntimeError): {error_detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        ) from e
    except Exception as e:
        error_detail = (
            f"Неожиданная ошибка при захвате изображений: {str(e)}. "
            f"Проверьте логи для подробностей."
        )
        logger.error(f"[API] Неожиданная ошибка захвата: {error_detail}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        ) from e

    try:
        record = CaptureSession(
            uid=request.uid,
            connection_class=request.connection_class,
            front_saved=result.front_saved,
            top_saved=result.top_saved,
            front_dir=result.front_dir,
            top_dir=result.top_dir,
            front_archive=result.front_archive,
            top_archive=result.top_archive,
            errors=result.errors,
            camera_config=request.model_dump(),
        )
        db.add(record)
        db.commit()
        logger.debug(f"[API] Сессия захвата сохранена в БД: ID={record.id}")
    except Exception as e:
        db.rollback()
        error_detail = f"Ошибка сохранения сессии захвата в БД: {str(e)}"
        logger.error(f"[API] {error_detail}", exc_info=True)
        # Не прерываем ответ, т.к. захват уже выполнен
        logger.warning(f"[API] Продолжаем без сохранения в БД")
    
    return result


@app.post(
    "/api/v1/cameras/test",
    response_model=list[CameraTestResult],
    tags=["cameras"],
)
async def camera_test(
    payload: CameraTestRequest,
    _: str = Depends(get_current_user),
):
    """Тестирует доступность камер."""
    logger.info(f"[API] Запрос на тестирование {len(payload.cameras)} камер")
    
    try:
        results = await run_in_threadpool(test_cameras, payload.cameras)
        successful = sum(1 for r in results if r.reachable)
        logger.info(
            f"[API] Тестирование завершено: {successful}/{len(results)} камер доступны"
        )
        return results
    except Exception as e:
        error_detail = f"Ошибка при тестировании камер: {str(e)}"
        logger.error(f"[API] {error_detail}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        ) from e


@app.post(
    "/api/v1/modbus/readings",
    response_model=ModbusReadResponse,
    tags=["modbus"],
)
async def modbus_readings(
    payload: ModbusReadRequest = Body(default=ModbusReadRequest()),
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ручное чтение значений Modbus (одноразовое)."""
    vars_count = len(payload.variables) if payload.variables else "default"
    logger.info(
        f"[API] Запрос на чтение Modbus: {vars_count} переменных, "
        f"device={settings.modbus_ip}:{settings.modbus_port}"
    )
    
    try:
        values: list[ModbusValue] = await run_in_threadpool(
            read_modbus,
            settings,
            payload.variables,
        )
        
        errors_in_values = [v for v in values if isinstance(v.value, str) and "Error" in str(v.value)]
        if errors_in_values:
            logger.warning(
                f"[API] При чтении Modbus обнаружены ошибки в {len(errors_in_values)} переменных"
            )
        
        logger.info(f"[API] Modbus чтение завершено: {len(values)} значений прочитано")
        
        response = ModbusReadResponse(
            timestamp=datetime.now(timezone.utc),
            values=values,
        )
    except RuntimeError as e:
        error_detail = (
            f"Ошибка подключения к Modbus устройству: {str(e)}. "
            f"Проверьте доступность устройства {settings.modbus_ip}:{settings.modbus_port}."
        )
        logger.error(f"[API] {error_detail}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail
        ) from e
    except Exception as e:
        error_detail = f"Неожиданная ошибка при чтении Modbus: {str(e)}"
        logger.error(f"[API] {error_detail}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        ) from e
    
    try:
        db.add(
            ModbusReading(
                timestamp=response.timestamp,
                values=[value.model_dump() for value in values],
                extra={
                    "variables": [v.model_dump() for v in payload.variables]
                    if payload.variables
                    else None,
                    "source": "manual_request",
                },
            )
        )
        db.commit()
        logger.debug(f"[API] Modbus чтение сохранено в БД")
    except Exception as e:
        db.rollback()
        logger.warning(f"[API] Ошибка сохранения Modbus чтения в БД: {e}")
        # Не прерываем ответ
    
    return response


@app.get(
    "/api/v1/modbus/poll/status",
    response_model=ModbusPollStatusResponse,
    tags=["modbus"],
)
async def modbus_poll_status(_: str = Depends(get_current_user)):
    """Get status of automatic Modbus polling."""
    poller = get_poller(settings)
    return ModbusPollStatusResponse(**poller.get_status())


@app.post("/api/v1/modbus/poll/start", tags=["modbus"])
async def modbus_poll_start(_: str = Depends(get_current_user)):
    """Start automatic Modbus polling."""
    poller = get_poller(settings)
    await poller.start()
    return {"message": "Modbus polling started", "status": poller.get_status()}


@app.post("/api/v1/modbus/poll/stop", tags=["modbus"])
async def modbus_poll_stop(_: str = Depends(get_current_user)):
    """Stop automatic Modbus polling."""
    poller = get_poller(settings)
    await poller.stop()
    return {"message": "Modbus polling stopped", "status": poller.get_status()}


@app.get("/api/v1/rail-grids", response_model=list[RailGridResponse], tags=["rail-grids"])
async def list_rail_grids(
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
):
    """Get list of rail grids."""
    grids = db.query(RailGrid).order_by(RailGrid.started_at.desc()).offset(offset).limit(limit).all()
    return grids


@app.get("/api/v1/rail-grids/{grid_uuid}", response_model=RailGridResponse, tags=["rail-grids"])
async def get_rail_grid(
    grid_uuid: str,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get rail grid by UUID."""
    grid = db.query(RailGrid).filter(RailGrid.uuid == grid_uuid).first()
    if not grid:
        raise HTTPException(status_code=404, detail="Rail grid not found")
    return grid


