"""Background job that polls qualified smart money signals and dispatches Mode 2 Telegram alerts."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from telegram.ext import ContextTypes

from app.config import get_settings
from app.db.mongo import get_db
from app.handlers.fomo import get_fomo_subscribed_chats
from app.handlers.radar_alert import RadarAlertFormatter

logger = logging.getLogger(__name__)


async def radar_alert_dispatcher_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Finds undispatched qualified signals and broadcasts to subscribed chats."""
    try:
        db = get_db()
    except Exception as e:
        logger.error("radar_dispatcher.db_error", extra={"error": str(e)})
        return

    # Find signals with score >= 80 and not dispatched yet
    try:
        signals = await db["token_signals"].find(
            {
                "score": {"$gte": 80},
                "dispatched": {"$ne": True},
            }
        ).to_list(length=10)
    except Exception as e:
        logger.error("radar_dispatcher.query_error", extra={"error": str(e)})
        return

    if not signals:
        return

    # Target chats: subscribed chats + admin_chat_id
    chats = set(get_fomo_subscribed_chats())
    admin_chat = get_settings().admin_chat_id
    if admin_chat:
        try:
            chats.add(int(admin_chat))
        except ValueError:
            chats.add(admin_chat)

    if not chats:
        logger.debug("radar_dispatcher: no subscribed chats found")
        return

    for doc in signals:
        text, reply_markup = RadarAlertFormatter.format_alert(doc)

        for chat_id in chats:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
                await asyncio.sleep(0.05)  # Throttling
            except Exception as e:
                logger.warning(
                    "radar_dispatcher.send_failed",
                    extra={"chat_id": chat_id, "error": str(e)},
                )

        try:
            await db["token_signals"].update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "dispatched": True,
                        "dispatched_at": time.time(),
                    }
                },
            )
        except Exception as e:
            logger.error(
                "radar_dispatcher.mark_dispatched_failed",
                extra={"signal_id": doc.get("_id"), "error": str(e)},
            )
