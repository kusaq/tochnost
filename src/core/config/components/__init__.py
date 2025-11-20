from core.config.components.base import BaseConfig
from core.config.components.db import DatabaseConfig
from core.config.components.redis import RedisConfig
from core.config.components.auth import AuthConfig


class ComponentsConfig(BaseConfig, DatabaseConfig, RedisConfig, AuthConfig):
    pass


__all__ = ["ComponentsConfig"]
