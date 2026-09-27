"""Poll activity of followed traders and notify on new trades."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram.ext import ContextTypes

from app.handlers.fomo import get_fomo_client, get_fomo_subscribed_chats
from app.services.fomo_client import FomoTokenExpiredError, TradeActivity, _NETWORK_NAMES

logger = logging.getLogger(__name__)

# user_id → set of activity IDs seen in last poll
_last_activity_ids: dict[str, set[str]] = {}
_initialized = False


def _fmt_usd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.2f}"


def _fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso


def _trade_emoji(trade_type: str) -> str:
    return "🟢 Mua" if trade_type == "DEPOSIT" else "🔴 Bán"


def _build_trade_msg(display_name: str, handle: str, activity: TradeActivity) -> str:
    network = _NETWORK_NAMES.get(activity.network_id, str(activity.network_id))
    profile = f"https://fomo.family/{handle}"
    action = _trade_emoji(activity.trade_type)
    sym = activity.token_symbol or "?"
    ca = f"`{activity.token_address}`"
    return (
        f"🔔 *Trade mới từ following*\n\n"
        f"👤 [{display_name}]({profile}) — {action} *{sym}*\n"
        f"🌐 Chain: {network}\n"
        f"🪙 Token: *{sym}*\n"
        f"📋 CA: {ca}\n"
        f"💰 Volume: *{_fmt_usd(activity.usd_amount)}*\n"
        f"⏰ {_fmt_time(activity.created_at)}"
    )


async def fomo_watching_alert_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    global _initialized

    chats = get_fomo_subscribed_chats()
    if not chats:
        return

    client = get_fomo_client()
    if client is None:
        return

    try:
        following = await client.get_following()
    except FomoTokenExpiredError:
        logger.warning("fomo.watching_alert.token_expired")
        for chat_id in chats:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ *Fomo Watching*: Token hết hạn. Dùng `/fomo token <new_token>` để cập nhật.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return
    except Exception:
        logger.exception("fomo.watching_alert.following_error")
        return

    if not following:
        return

    messages: list[str] = []

    for trader in following:
        try:
            activities = await client.get_user_activity(trader.id, limit=20)
        except FomoTokenExpiredError:
            raise
        except Exception:
            logger.exception("fomo.watching_alert.activity_error", extra={"user_id": trader.id})
            continue

        current_ids = {a.id for a in activities}
        prev_ids = _last_activity_ids.get(trader.id, set())

        if not _initialized:
            # Seed on first run — no notifications
            _last_activity_ids[trader.id] = current_ids
            continue

        new_ids = current_ids - prev_ids
        if new_ids:
            for activity in activities:
                if activity.id in new_ids:
                    messages.append(_build_trade_msg(trader.display_name, trader.user_handle, activity))

        _last_activity_ids[trader.id] = current_ids

    if not _initialized:
        _initialized = True
        logger.info("fomo.watching_alert.initialized", extra={"traders": len(following)})
        return

    for msg in messages:
        for chat_id in chats:
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            except Exception:
                logger.exception("fomo.watching_alert.send_failed", extra={"chat_id": chat_id})
