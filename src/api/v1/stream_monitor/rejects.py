"""Учёт отклонённых входящих запросов (HTTP 422) в мониторе потока.

Валидация Pydantic отрабатывает ДО тела хендлера, поэтому битый пакет датчика
никогда не доходил до stream_monitor: FastAPI отдавал 422, а в мониторе была
тишина — источник выглядел просто «протухшим». При смене контракта прошивки
(например, поля забега из ADR-0010) это означало полную слепоту: непонятно ни
что именно пришло, ни с какого момента поток встал.

Sensor1 шлёт ~1000 пакетов/с. Если контракт разъехался, битыми будут ВСЕ, и
поштучная запись за секунды вытеснила бы весь буфер и залила WS. Поэтому
события троттлятся по сигнатуре ошибки: одно событие на сигнатуру в окно,
остальные копятся в `repeat_count`.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from api.v1.stream_monitor.service import stream_monitor

# Тот же парсер ENV, что и у буферов монитора: пустая/битая строка → дефолт.
from api.v1.stream_monitor.state import STREAM_MONITOR_STATE, _env_int

logger = logging.getLogger(__name__)

REJECT_EVENT_TYPE = "ingest_rejected"

# Не чаще одного события на сигнатуру за окно (остальное — в repeat_count).
REJECT_WINDOW_SEC = _env_int("STREAM_MONITOR_REJECT_WINDOW_SEC", 10)
# Обрезка сырого тела: смотрим на структуру пакета, а не храним мегабайты.
REJECT_BODY_LIMIT = _env_int("STREAM_MONITOR_REJECT_BODY_LIMIT", 4096)
# Потолок словаря сигнатур, чтобы фаззинг/мусор не растил его безгранично.
REJECT_MAX_SIGNATURES = _env_int("STREAM_MONITOR_REJECT_MAX_SIGNATURES", 200)
# Pydantic умеет выдать ошибку на каждое поле — в payload кладём первые N.
REJECT_MAX_ERRORS = 20


@dataclass(slots=True)
class _SignatureState:
    first_seen_at: str
    last_emit_at: float
    pending: int = 0


class _RejectThrottle:
    """Дедуп отклонений по сигнатуре ошибки."""

    def __init__(self) -> None:
        self._seen: dict[str, _SignatureState] = {}

    def observe(self, signature: str, now: float) -> tuple[int, str] | None:
        """(repeat_count, first_seen_at), если событие надо записать, иначе None.

        repeat_count — сколько отклонённых запросов покрывает это событие:
        1 для первого, накопленный хвост для последующих.
        """
        state = self._seen.get(signature)
        if state is None:
            if len(self._seen) >= REJECT_MAX_SIGNATURES:
                self._evict_oldest()
            first_seen_at = datetime.now(timezone.utc).isoformat()
            self._seen[signature] = _SignatureState(first_seen_at=first_seen_at, last_emit_at=now)
            return 1, first_seen_at

        state.pending += 1
        if now - state.last_emit_at < REJECT_WINDOW_SEC:
            return None
        repeat_count = state.pending
        state.pending = 0
        state.last_emit_at = now
        return repeat_count, state.first_seen_at

    def _evict_oldest(self) -> None:
        oldest = min(self._seen, key=lambda sig: self._seen[sig].last_emit_at)
        self._seen.pop(oldest, None)

    def reset(self) -> None:
        self._seen.clear()


reject_throttle = _RejectThrottle()


def _signature(method: str, path: str, errors: list[dict[str, Any]]) -> str:
    parts = sorted(
        "{}:{}".format(
            ".".join(str(x) for x in error.get("loc", ())),
            error.get("type", ""),
        )
        for error in errors
    )
    raw = f"{method} {path} " + "|".join(parts)
    return hashlib.blake2s(raw.encode("utf-8"), digest_size=6).hexdigest()


def _peek_sensor_id(body: bytes) -> int | None:
    """sensor_id из сырого тела — до Pydantic, поэтому «как есть»."""
    try:
        parsed = json.loads(body)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("sensor_id")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _source_for(path: str, body: bytes) -> tuple[str, int | None]:
    """(source, sensor_id). Тело парсим только там, где source от него зависит."""
    if path.endswith("/sensor/second"):
        return "modbus", None
    if path.endswith("/sensor/first"):
        sensor_id = _peek_sensor_id(body)
        # Тело могло не распарситься — тогда sensor_id неизвестен. Кладём под
        # пост 1 (частый случай), истина всё равно лежит в payload.sensor_id.
        return ("sensor1_post2" if sensor_id == 2 else "sensor1_post1"), sensor_id
    return "http", None


def _summary(method: str, path: str, errors: list[dict[str, Any]], repeat_count: int) -> str:
    head = errors[0] if errors else {}
    loc = ".".join(str(x) for x in head.get("loc", ()) if x != "body")
    kind = head.get("type", "invalid")
    detail = f"{loc}: {kind}" if loc else kind
    extra = f" (+{len(errors) - 1})" if len(errors) > 1 else ""
    tail = f" · ×{repeat_count}" if repeat_count > 1 else ""
    return f"422 {method} {path} · {detail}{extra}{tail}"


async def record_rejected_request(
    *,
    method: str,
    path: str,
    body: bytes,
    errors: list[dict[str, Any]],
) -> None:
    """Пишет отклонённый запрос в монитор с троттлингом по сигнатуре."""
    source, sensor_id = _source_for(path, body)
    # Счётчик — до троттлинга: событий в ленте мало, а знать надо, отклонён
    # один пакет или весь поток.
    STREAM_MONITOR_STATE.note_rejected(source)

    signature = _signature(method, path, errors)
    observed = reject_throttle.observe(signature, time.monotonic())
    if observed is None:
        return
    repeat_count, first_seen_at = observed

    raw_body = body.decode("utf-8", errors="replace")
    truncated = len(raw_body) > REJECT_BODY_LIMIT
    if truncated:
        raw_body = raw_body[:REJECT_BODY_LIMIT]

    payload: dict[str, Any] = {
        "method": method,
        "path": path,
        "status": 422,
        "sensor_id": sensor_id,
        "errors": errors[:REJECT_MAX_ERRORS],
        "errors_total": len(errors),
        "raw_body": raw_body,
        "raw_body_truncated": truncated,
        "repeat_count": repeat_count,
        "signature": signature,
        "first_seen_at": first_seen_at,
        "throttle_window_sec": REJECT_WINDOW_SEC,
    }

    await stream_monitor.record_event(
        source=source,
        payload=payload,
        event_type=REJECT_EVENT_TYPE,
        summary=_summary(method, path, errors, repeat_count),
    )
