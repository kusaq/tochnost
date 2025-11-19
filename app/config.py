from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    api_title: str = Field(
        default="RZhD Data Service",
        alias="API_TITLE",
        description="Title shown in the FastAPI docs.",
    )
    api_version: str = Field(
        default="1.0.0",
        alias="API_VERSION",
        description="API version string.",
    )

    secret_key: str = Field(
        default="change-me",
        alias="API_SECRET_KEY",
        description="Secret key for signing JWT tokens.",
    )
    algorithm: str = Field(
        default="HS256",
        alias="API_TOKEN_ALGORITHM",
        description="Algorithm used for JWT tokens.",
    )
    access_token_expire_minutes: int = Field(
        default=60,
        alias="API_TOKEN_TTL_MIN",
        description="Access token lifetime in minutes.",
    )
    api_username: str = Field(
        default="admin",
        alias="API_USERNAME",
        description="Username for the built-in auth user.",
    )
    api_password: Optional[str] = Field(
        default=None,
        alias="API_PASSWORD",
        description="Plain-text password (use only for development).",
    )
    api_password_hash: Optional[str] = Field(
        default=None,
        alias="API_PASSWORD_HASH",
        description="Pre-hashed password using bcrypt.",
    )

    data_root: str = Field(
        default="data",
        alias="DATA_ROOT",
        description="Base directory for storing captured images.",
    )

    hikvision_user: str = Field(default="admin", alias="HIKVISION_USER")
    hikvision_pass: str = Field(default="password", alias="HIKVISION_PASS")
    hikvision_rtsp_port: str = Field(default="554", alias="HIKVISION_RTSP_PORT")
    hikvision_top_ip: str = Field(default="192.168.1.104", alias="HIKVISION_TOP_IP")
    hikvision_front_ip: str = Field(default="192.168.1.105", alias="HIKVISION_FRONT_IP")
    hikvision_top_channel: str = Field(default="101", alias="HIKVISION_TOP_CHANNEL")
    hikvision_front_channel: str = Field(default="101", alias="HIKVISION_FRONT_CHANNEL")
    
    # Дополнительные настройки Hikvision для захвата
    hikvision_capture_interval: int = Field(
        default=3,
        alias="HIKVISION_CAPTURE_INTERVAL",
        description="Интервал захвата кадров в секундах.",
    )
    hikvision_capture_duration_min: float = Field(
        default=90.0,
        alias="HIKVISION_CAPTURE_DURATION_MIN",
        description="Длительность захвата в минутах.",
    )
    hikvision_preview: bool = Field(
        default=False,
        alias="HIKVISION_PREVIEW",
        description="Показывать превью при захвате.",
    )
    hikvision_crop_top: int = Field(
        default=0,
        alias="HIKVISION_CROP_TOP",
        description="Обрезка сверху в пикселях.",
    )
    hikvision_crop_bottom: int = Field(
        default=0,
        alias="HIKVISION_CROP_BOTTOM",
        description="Обрезка снизу в пикселях.",
    )
    hikvision_crop_left: int = Field(
        default=0,
        alias="HIKVISION_CROP_LEFT",
        description="Обрезка слева в пикселях.",
    )
    hikvision_crop_right: int = Field(
        default=0,
        alias="HIKVISION_CROP_RIGHT",
        description="Обрезка справа в пикселях.",
    )
    hikvision_jpeg_quality: int = Field(
        default=85,
        alias="HIKVISION_JPEG_QUALITY",
        ge=10,
        le=100,
        description="Качество JPEG (10-100).",
    )
    hikvision_archive_after_capture: bool = Field(
        default=True,
        alias="HIKVISION_ARCHIVE_AFTER_CAPTURE",
        description="Создавать архив после захвата.",
    )
    hikvision_archive_remove_originals: bool = Field(
        default=False,
        alias="HIKVISION_ARCHIVE_REMOVE_ORIGINALS",
        description="Удалять оригиналы после архивации.",
    )

    modbus_ip: str = Field(default="192.168.1.106", alias="MODBUS_IP")
    modbus_port: int = Field(default=502, alias="MODBUS_PORT")
    modbus_unit_id: int = Field(default=1, alias="MODBUS_UNIT_ID")
    modbus_timeout: float = Field(default=3.0, alias="MODBUS_TIMEOUT")
    modbus_poll_interval_sec: float = Field(
        default=1.0,
        alias="MODBUS_POLL_INTERVAL_SEC",
        description="Interval in seconds for automatic Modbus polling during active grid.",
    )
    modbus_detection_interval_sec: float = Field(
        default=15.0,
        alias="MODBUS_DETECTION_INTERVAL_SEC",
        description="Interval in seconds for detecting new rail grid movement.",
    )
    modbus_poll_enabled: bool = Field(
        default=True,
        alias="MODBUS_POLL_ENABLED",
        description="Enable automatic Modbus polling on startup.",
    )

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/rzd",
        alias="DATABASE_URL",
        description="SQLAlchemy connection string for PostgreSQL.",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()  # type: ignore[call-arg]


