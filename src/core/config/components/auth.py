from pydantic_settings import BaseSettings, SettingsConfigDict

from core.config.constants import ENV_FILE_PATH


class AuthConfig(BaseSettings):
    # JWT settings
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    jwt_renew_threshold_minutes: int = 10

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding='utf-8',
    )
