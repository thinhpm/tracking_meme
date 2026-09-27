from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    api_base_url: str = "http://api:8000"
    log_level: str = "info"
    fomo_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
