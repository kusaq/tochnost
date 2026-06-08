"""Отправка серии снимков с камеры дашборда в Telegram при уходе РШР с поста 2."""

from __future__ import annotations

import asyncio
import logging

import requests

from api.v1.camera.service import capture_rail_jpeg_once
from core.config import settings

logger = logging.getLogger(__name__)

_active_bursts: set[int] = set()


def _telegram_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def send_telegram_photo(jpeg_bytes: bytes, caption: str) -> None:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendPhoto"
    response = requests.post(
        url,
        data={"chat_id": settings.telegram_chat_id, "caption": caption},
        files={"photo": ("rail.jpg", jpeg_bytes, "image/jpeg")},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Telegram sendPhoto failed ({response.status_code}): {response.text[:500]}"
        )


async def _rail_burst_worker(rail_id: int) -> None:
    count = settings.telegram_rail_burst_count
    interval = settings.telegram_rail_burst_interval_sec
    logger.info(
        "Rail burst started for RSHR #%s: %s photos every %ss",
        rail_id,
        count,
        interval,
    )
    try:
        for frame_no in range(1, count + 1):
            try:
                jpeg_bytes = await asyncio.to_thread(capture_rail_jpeg_once)
                caption = f"РШР #{rail_id} — кадр {frame_no}/{count}"
                await asyncio.to_thread(send_telegram_photo, jpeg_bytes, caption)
            except Exception:
                logger.exception(
                    "Rail burst photo failed for RSHR #%s (%s/%s)",
                    rail_id,
                    frame_no,
                    count,
                )
            if frame_no < count:
                await asyncio.sleep(interval)
    finally:
        _active_bursts.discard(rail_id)
        logger.info("Rail burst finished for RSHR #%s", rail_id)


def schedule_rail_departure_burst(rail_id: int) -> None:
    """Запускает фоновую отправку снимков при уходе РШР с поста 2."""
    if not settings.telegram_enabled:
        return
    if not _telegram_configured():
        logger.warning(
            "Telegram burst skipped for RSHR #%s: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing",
            rail_id,
        )
        return
    if rail_id in _active_bursts:
        logger.info("Rail burst already running for RSHR #%s", rail_id)
        return

    _active_bursts.add(rail_id)
    asyncio.create_task(_rail_burst_worker(rail_id))
