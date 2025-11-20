from pydantic_settings import BaseSettings, SettingsConfigDict

from core.config.constants import ENV_FILE_PATH


class BaseConfig(BaseSettings):
    DEBUG: bool = True
    app_host: str = "0.0.0.0"
    public_url: str = "http://localhost:8000"
    secret_key: str
    app_port: int = 8000
    workers: int = 1
    reload: bool = False

    # CORS settings
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding='utf-8',
    )
