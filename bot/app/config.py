from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    api_base_url: str = "http://api:8000"
    log_level: str = "info"
    fomo_token: str = ""
    zerion_api_key: str = ""

    # Database & Radar
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "tracking_meme"
    solana_rpc_url: str = ""
    solana_ws_url: str = ""
    fomo_auto_refresh_enabled: bool = True
    fomo_refresh_interval_minutes: int = 45


@lru_cache
def get_settings() -> Settings:
    return Settings()
