from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.config.constants import ENV_FILE_PATH


class TelegramConfig(BaseSettings):
    telegram_enabled: bool = Field(default=False)
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")
    telegram_rail_burst_count: int = Field(default=20, ge=1, le=120)
    telegram_rail_burst_interval_sec: float = Field(default=1.0, ge=0.2, le=10.0)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
    )
