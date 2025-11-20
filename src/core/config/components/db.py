from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.config.constants import ENV_FILE_PATH


class DatabaseConfig(BaseSettings):
    postgres_host: str = Field(default='localhost')
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default='postgres')
    postgres_password: str = Field(default='postgres')
    postgres_db: str = Field(default='postgres')

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding='utf-8',
    )

    @computed_field(return_type=str)
    def DATABASE_URL(self): # noqa
        return (f'postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@'
                f'{self.postgres_host}:{self.postgres_port}/{self.postgres_db}'
                f'?async_fallback=True')
