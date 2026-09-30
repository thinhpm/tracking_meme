import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.jobs.fomo_token_refresh import fomo_token_monitor_job, check_token_health


def make_jwt(exp_timestamp: int) -> str:
    header = base64.b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    payload = base64.b64encode(json.dumps({"exp": exp_timestamp}).encode()).decode().rstrip("=")
    signature = "signature"
    return f"{header}.{payload}.{signature}"


def test_check_token_health_valid():
    now = int(time.time())
    token = make_jwt(now + 1800)  # 30m remaining
    health = check_token_health(token)
    assert health["status"] == "ok"
    assert health["remaining_seconds"] > 1700


def test_check_token_health_expiring_soon():
    now = int(time.time())
    token = make_jwt(now + 300)  # 5m remaining (< 10m)
    health = check_token_health(token)
    assert health["status"] == "expiring_soon"
    assert health["remaining_seconds"] <= 300


def test_check_token_health_expired():
    now = int(time.time())
    token = make_jwt(now - 10)
    health = check_token_health(token)
    assert health["status"] == "expired"


@pytest.mark.asyncio
async def test_fomo_token_monitor_job_sends_alert_when_expiring_soon():
    now = int(time.time())
    token = make_jwt(now + 300)  # 5 mins left

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    mock_settings = MagicMock()
    mock_settings.admin_chat_id = "123456789"

    mock_provider = MagicMock()
    mock_provider.get_token = AsyncMock(return_value=token)

    with patch("app.jobs.fomo_token_refresh.get_settings", return_value=mock_settings), \
         patch("app.jobs.fomo_token_refresh.get_token_provider", return_value=mock_provider), \
         patch("app.jobs.fomo_token_refresh._last_alert_sent", 0):

        await fomo_token_monitor_job(context)

        context.bot.send_message.assert_called_once()
        call_kwargs = context.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == "123456789"
        assert "sắp hết hạn" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_fomo_token_monitor_job_no_alert_when_valid():
    now = int(time.time())
    token = make_jwt(now + 1800)  # 30 mins left

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    mock_settings = MagicMock()
    mock_settings.admin_chat_id = "123456789"

    mock_provider = MagicMock()
    mock_provider.get_token = AsyncMock(return_value=token)

    with patch("app.jobs.fomo_token_refresh.get_settings", return_value=mock_settings), \
         patch("app.jobs.fomo_token_refresh.get_token_provider", return_value=mock_provider):

        await fomo_token_monitor_job(context)

        context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_fomo_token_monitor_job_cooldown_prevents_spam():
    now = int(time.time())
    token = make_jwt(now + 300)

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    mock_settings = MagicMock()
    mock_settings.admin_chat_id = "123456789"

    mock_provider = MagicMock()
    mock_provider.get_token = AsyncMock(return_value=token)

    with patch("app.jobs.fomo_token_refresh.get_settings", return_value=mock_settings), \
         patch("app.jobs.fomo_token_refresh.get_token_provider", return_value=mock_provider), \
         patch("app.jobs.fomo_token_refresh._last_alert_sent", now):  # alerted just now

        await fomo_token_monitor_job(context)

        context.bot.send_message.assert_not_called()
