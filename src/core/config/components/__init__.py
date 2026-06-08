from core.config.components.base import BaseConfig
from core.config.components.db import DatabaseConfig
from core.config.components.redis import RedisConfig
from core.config.components.auth import AuthConfig
from core.config.components.camera import CameraConfig
from core.config.components.telegram import TelegramConfig


class ComponentsConfig(
    BaseConfig, DatabaseConfig, RedisConfig, AuthConfig, CameraConfig, TelegramConfig
):
    pass


__all__ = ["ComponentsConfig"]
