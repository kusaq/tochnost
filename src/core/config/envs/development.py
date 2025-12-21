from pydantic_settings import BaseSettings, SettingsConfigDict

from core.config.constants import ENV_FILE_PATH


class DevelopmentConfig(BaseSettings):
    DEBUG: bool = True
    reload: bool = False
    workers: int = 1

    docs_url: str = "/docs"
    redoc_url: str = "/redoc"

    # CORS settings
    cors_origins: list[str] = [
        "http://localhost",
        "https://rzd-snowy.vercel.app"
    ]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding='utf-8',
    )
