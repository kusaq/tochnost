from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.config.constants import ENV_FILE_PATH


class CameraConfig(BaseSettings):
    camera_enabled: bool = Field(default=False)
    camera_mock: bool = Field(default=False)
    camera_capture_interval_sec: float = Field(default=5.0, ge=0.5)
    camera_motion_threshold: float = Field(default=8.0, ge=0.0)

    hikvision_user: str = Field(default="")
    hikvision_pass: str = Field(default="")
    hikvision_front_ip: str = Field(default="")
    hikvision_rtsp_port: int = Field(default=554)
    hikvision_front_channel: str = Field(default="101")
    hikvision_rtsp_transport: str = Field(default="tcp")

    hikvision_crop_top: int = Field(default=0, ge=0)
    hikvision_crop_bottom: int = Field(default=0, ge=0)
    hikvision_crop_left: int = Field(default=0, ge=0)
    hikvision_crop_right: int = Field(default=0, ge=0)
    hikvision_jpeg_quality: int = Field(default=75, ge=10, le=100)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
    )
