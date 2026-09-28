import os
from unittest.mock import patch

from app.config import Settings


def test_settings_defaults_without_anthropic_api_key() -> None:
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)
        assert settings.anthropic_api_key == ""
        assert settings.gemini_service_url == "http://localhost:8000"
        assert settings.gemini_service_provider == ""
        assert settings.gemini_service_model == ""


def test_settings_custom_gemini_config() -> None:
    custom_env = {
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "GEMINI_SERVICE_URL": "http://custom-host:9000",
        "GEMINI_SERVICE_PROVIDER": "openrouter",
        "GEMINI_SERVICE_MODEL": "gemini-2.5-flash",
    }
    with patch.dict(os.environ, custom_env, clear=True):
        settings = Settings(_env_file=None)
        assert settings.anthropic_api_key == "sk-ant-test"
        assert settings.gemini_service_url == "http://custom-host:9000"
        assert settings.gemini_service_provider == "openrouter"
        assert settings.gemini_service_model == "gemini-2.5-flash"
