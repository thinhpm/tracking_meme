from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    gemini_service_url: str = "http://localhost:8000"
    gemini_service_provider: str = ""
    gemini_service_model: str = ""
    goplus_api_key: str = ""
    log_level: str = "info"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
