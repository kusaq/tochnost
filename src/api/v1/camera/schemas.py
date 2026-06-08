from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CameraSnapshotRead(BaseModel):
    captured_at: datetime | None = Field(default=None, description="Время захвата кадра")
    image_base64: str | None = Field(default=None, description="JPEG в base64")
    motion_detected: bool = Field(default=False, description="Обнаружено движение")
    motion_score: float | None = Field(default=None, description="Средняя разница кадров (grayscale absdiff)")
    status: Literal["ok", "error", "mock", "disabled", "waiting"] = Field(
        default="waiting",
        description="Статус последнего захвата",
    )
    error_message: str | None = Field(default=None, description="Описание ошибки при status=error")
