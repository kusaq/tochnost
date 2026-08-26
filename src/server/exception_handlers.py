"""Глобальные обработчики ошибок FastAPI.

Единственная задача — сделать отклонённые запросы наблюдаемыми в мониторе
потока. Ответ клиенту не меняется: делегируем штатному хендлеру FastAPI,
чтобы форма 422 оставалась ровно такой же (и не зависела от версии).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

from api.v1.stream_monitor.rejects import record_rejected_request

logger = logging.getLogger(__name__)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> Response:
    try:
        errors = jsonable_encoder(exc.errors())
    except Exception:  # pragma: no cover — не даём диагностике уронить ответ
        errors = []

    body = b""
    try:
        # Тело уже прочитано и закэшировано FastAPI при валидации, поэтому
        # повторный body() отдаёт его же. Если валидация упала на query/path,
        # стрим не читался — Starlette бросит RuntimeError, тело останется пустым.
        body = await request.body()
    except Exception:
        pass

    try:
        await record_rejected_request(
            method=request.method,
            path=request.url.path,
            body=body,
            errors=errors,
        )
    except Exception as exc_record:
        logger.warning("failed to record rejected request: %r", exc_record)

    return await request_validation_exception_handler(request, exc)


def init_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
