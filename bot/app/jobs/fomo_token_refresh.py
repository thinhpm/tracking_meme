"""Periodic job to monitor Fomo auth token expiration and alert admin."""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from telegram.ext import ContextTypes

from app.config import get_settings
from app.db.mongo import get_db
from app.services.fomo_client import FomoTokenProvider

logger = logging.getLogger(__name__)

_last_alert_sent: float = 0
_ALERT_COOLDOWN_SECONDS: float = 900  # 15 minutes cooldown
_provider: FomoTokenProvider | None = None


def get_token_provider() -> FomoTokenProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        db = None
        try:
            db = get_db()
        except Exception:
            pass
        _provider = FomoTokenProvider(
            db=db,
            session_file=settings.fomo_session_file,
            fallback_token=settings.fomo_token,
            refresh_token=settings.fomo_refresh_token,
            privy_access_token=settings.fomo_privy_access_token,
        )
    return _provider


def check_token_health(token: str) -> dict[str, Any]:
    if not token or not isinstance(token, str):
        return {"status": "expired", "remaining_seconds": 0, "exp": 0}

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {"status": "expired", "remaining_seconds": 0, "exp": 0}
        payload = parts[1]
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")))
        exp = int(data.get("exp", 0))
        now = int(time.time())
        remaining = exp - now

        if remaining <= 0:
            return {"status": "expired", "remaining_seconds": 0, "exp": exp}
        elif remaining <= 600:  # <= 10 minutes
            return {"status": "expiring_soon", "remaining_seconds": remaining, "exp": exp}
        else:
            return {"status": "ok", "remaining_seconds": remaining, "exp": exp}
    except Exception:
        return {"status": "expired", "remaining_seconds": 0, "exp": 0}


async def fomo_token_monitor_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    global _last_alert_sent

    settings = get_settings()
    admin_chat = settings.admin_chat_id
    if not admin_chat:
        logger.debug("fomo.token_monitor: ADMIN_CHAT_ID is not set, skipping alerts.")
        return

    provider = get_token_provider()
    try:
        token = await provider.get_token()
    except Exception as e:
        logger.warning("fomo.token_monitor.get_token_failed", extra={"error": str(e)})
        token = ""

    health = check_token_health(token)
    status = health["status"]

    if status in ("expiring_soon", "expired"):
        # 1. Proactively auto-refresh if provider supports it
        if hasattr(provider, "refresh_session"):
            try:
                new_token = await provider.refresh_session()
                if new_token:
                    new_health = check_token_health(new_token)
                    if new_health["status"] == "ok":
                        logger.info("fomo.token_monitor: successfully auto-refreshed session token via Privy")
                        return
            except Exception as e:
                logger.warning("fomo.token_monitor.auto_refresh_failed", extra={"error": str(e)})

        now = time.time()
        if now - _last_alert_sent < _ALERT_COOLDOWN_SECONDS:
            logger.info("fomo.token_monitor: alert suppressed due to cooldown")
            return

        if status == "expired":
            msg = (
                "⚠️ *Cảnh báo FOMO Token*\n\n"
                "Token đã *hết hạn*! Hệ thống không thể fetch dữ liệu từ Fomo.\n"
                "Vui lòng cập nhật token mới bằng lệnh:\n"
                "`/fomo token <jwt>`"
            )
        else:
            mins = max(1, int(health["remaining_seconds"] // 60))
            msg = (
                f"⚠️ *Cảnh báo FOMO Token*\n\n"
                f"Token Fomo sắp hết hạn trong *{mins} phút*!\n"
                "Vui lòng cập nhật token mới bằng lệnh:\n"
                "`/fomo token <jwt>`"
            )

        try:
            await context.bot.send_message(chat_id=admin_chat, text=msg, parse_mode="Markdown")
            _last_alert_sent = now
            logger.info("fomo.token_monitor: alert sent to admin", extra={"admin_chat": admin_chat, "status": status})
        except Exception as e:
            logger.error("fomo.token_monitor: failed to send alert", extra={"error": str(e)})
