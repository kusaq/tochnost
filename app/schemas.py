from datetime import datetime
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class CaptureRequest(BaseModel):
    uid: str = Field(..., description="Rail element identifier.")
    connection_class: str = Field(..., description="Connection class folder.")
    use_default_cameras: bool = Field(
        default=True,
        description="Use Hikvision defaults from environment.",
    )
    top_camera_url: Optional[str] = Field(
        default=None, description="Optional override for the top camera source."
    )
    front_camera_url: Optional[str] = Field(
        default=None, description="Optional override for the front camera source."
    )
    front_count: int = Field(default=3, ge=1, le=2000)
    top_count: int = Field(default=1, ge=1, le=2000)
    interval_sec: int = Field(default=3, ge=1, le=3600)
    top_interval_sec: Optional[int] = Field(default=None, ge=1, le=3600)
    data_root: Optional[str] = Field(
        default=None,
        description="Override default data directory (absolute or relative).",
    )
    show_preview: Optional[bool] = Field(default=None, description="Показывать превью (если не указано, используется из .env)")
    crop_top: Optional[int] = Field(default=None, ge=0, description="Обрезка сверху (если не указано, используется из .env)")
    crop_bottom: Optional[int] = Field(default=None, ge=0, description="Обрезка снизу (если не указано, используется из .env)")
    crop_left: Optional[int] = Field(default=None, ge=0, description="Обрезка слева (если не указано, используется из .env)")
    crop_right: Optional[int] = Field(default=None, ge=0, description="Обрезка справа (если не указано, используется из .env)")
    jpeg_quality: Optional[int] = Field(default=None, ge=10, le=100, description="Качество JPEG (если не указано, используется из .env)")
    archive_after_capture: Optional[bool] = Field(default=None, description="Архивировать после захвата (если не указано, используется из .env)")
    archive_remove_originals: Optional[bool] = Field(default=None, description="Удалять оригиналы после архивации (если не указано, используется из .env)")


class CaptureResponse(BaseModel):
    front_dir: str
    top_dir: str
    front_saved: int
    top_saved: int
    errors: List[str]
    front_archive: Optional[str] = None
    top_archive: Optional[str] = None


class CameraTarget(BaseModel):
    label: Optional[str] = None
    url: str


class CameraTestResult(BaseModel):
    label: Optional[str]
    url: str
    reachable: bool
    message: str


class CameraTestRequest(BaseModel):
    cameras: List[CameraTarget]


class ModbusVariableConfig(BaseModel):
    name: str
    address: int
    count: int = Field(default=1, ge=1, le=10)
    value_type: Literal["int", "float_swapped", "raw"] = "int"


class ModbusValue(BaseModel):
    name: str
    address: int
    raw_registers: List[int]
    value: Union[int, float, str, None]


class ModbusReadRequest(BaseModel):
    variables: Optional[List[ModbusVariableConfig]] = None


class ModbusReadResponse(BaseModel):
    timestamp: datetime
    values: List[ModbusValue]


class ModbusPollStatusResponse(BaseModel):
    running: bool
    detection_mode: bool
    current_rail_grid_uuid: Optional[str] = None
    baseline_established: bool
    interval_sec: float
    poll_count: int
    last_success_time: Optional[str] = None
    last_error: Optional[str] = None


class RailGridResponse(BaseModel):
    id: int
    uuid: str
    connection_class: Optional[str] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    extra: dict = {}
    
    class Config:
        from_attributes = True



