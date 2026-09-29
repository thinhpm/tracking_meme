import os
import pytest
from app.config import Settings


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "mock_token")
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGODB_DB_NAME", raising=False)
    monkeypatch.delenv("SOLANA_RPC_URL", raising=False)
    monkeypatch.delenv("SOLANA_WS_URL", raising=False)
    monkeypatch.delenv("FOMO_AUTO_REFRESH_ENABLED", raising=False)
    monkeypatch.delenv("FOMO_REFRESH_INTERVAL_MINUTES", raising=False)

    settings = Settings(_env_file=None)
    assert settings.telegram_bot_token == "mock_token"
    assert settings.mongodb_uri == "mongodb://localhost:27017"
    assert settings.mongodb_db_name == "tracking_meme"
    assert settings.solana_rpc_url == ""
    assert settings.solana_ws_url == ""
    assert settings.fomo_auto_refresh_enabled is True
    assert settings.fomo_refresh_interval_minutes == 45


def test_settings_custom_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "mock_token")
    monkeypatch.setenv("MONGODB_URI", "mongodb://custom_host:27018")
    monkeypatch.setenv("MONGODB_DB_NAME", "custom_db")
    monkeypatch.setenv("SOLANA_RPC_URL", "https://custom-solana-rpc.com")
    monkeypatch.setenv("SOLANA_WS_URL", "wss://custom-solana-ws.com")
    monkeypatch.setenv("FOMO_AUTO_REFRESH_ENABLED", "false")
    monkeypatch.setenv("FOMO_REFRESH_INTERVAL_MINUTES", "30")

    settings = Settings()
    assert settings.mongodb_uri == "mongodb://custom_host:27018"
    assert settings.mongodb_db_name == "custom_db"
    assert settings.solana_rpc_url == "https://custom-solana-rpc.com"
    assert settings.solana_ws_url == "wss://custom-solana-ws.com"
    assert settings.fomo_auto_refresh_enabled is False
    assert settings.fomo_refresh_interval_minutes == 30
