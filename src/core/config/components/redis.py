from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.config.constants import ENV_FILE_PATH


class RedisConfig(BaseSettings):
    redis_password: str = Field(default="redis")
    redis_host: str = Field(default='localhost')
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding='utf-8',
    )

    @computed_field(return_type=str)
    def REDIS_URL(self): # noqa
        return f'redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}'
