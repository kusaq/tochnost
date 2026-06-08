from core.config.components.base import BaseConfig
from core.config.components.db import DatabaseConfig
from core.config.components.redis import RedisConfig
from core.config.components.auth import AuthConfig
from core.config.components.camera import CameraConfig


class ComponentsConfig(BaseConfig, DatabaseConfig, RedisConfig, AuthConfig, CameraConfig):
    pass


__all__ = ["ComponentsConfig"]
