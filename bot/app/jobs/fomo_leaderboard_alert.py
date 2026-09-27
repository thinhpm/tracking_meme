"""Poll fomo.family leaderboard and notify on rank changes / new top-10 entries."""
from __future__ import annotations

import logging

from telegram.ext import ContextTypes

from app.handlers.fomo import get_fomo_client, get_fomo_subscribed_chats
from app.services.fomo_client import FomoTokenExpiredError, Trader

logger = logging.getLogger(__name__)

_TOP_N = 10  # watch top 10 traders

# Snapshot: trader_id → rank
_last_ranks: dict[str, int] = {}
# Snapshot: trader_id → set of token addresses in topHoldings
_last_holdings: dict[str, set[str]] = {}

_RANK_JUMP_THRESHOLD = 3  # notify if rank improves by >= this


def _fmt_usd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


def _fomo_profile_url(handle: str) -> str:
    return f"https://fomo.family/{handle}"


def _build_new_entry_msg(trader: Trader) -> str:
    holdings_lines = ""
    if trader.top_holdings:
        lines = []
        for h in trader.top_holdings:
            lines.append(f"  • `{h.token_address}` — val: {_fmt_usd(h.value_usd)} | pnl: {_fmt_usd(h.pnl_usd)}")
        holdings_lines = "\n" + "\n".join(lines)

    return (
        f"🏆 *Trader mới vào Top {_TOP_N} — Fomo*\n\n"
        f"*#{trader.rank} [{trader.display_name}]({_fomo_profile_url(trader.user_handle)})*\n"
        f"💰 Total PnL: *{_fmt_usd(trader.total_pnl)}*\n"
        f"📊 Trades: {trader.num_trades:,} | Vol: {_fmt_usd(trader.total_volume)}\n"
        f"👥 Followers: {trader.followers:,}\n"
        f"🔑 Top Holdings:{holdings_lines if holdings_lines else ' _Chưa có_'}"
    )


def _build_rank_jump_msg(trader: Trader, old_rank: int) -> str:
    return (
        f"🚀 *Rank nhảy — Fomo Leaderboard*\n\n"
        f"*[{trader.display_name}]({_fomo_profile_url(trader.user_handle)})* "
        f"#{old_rank} → *#{trader.rank}* ↑{old_rank - trader.rank}\n"
        f"💰 Total PnL: *{_fmt_usd(trader.total_pnl)}*\n"
        f"📊 Trades: {trader.num_trades:,}"
    )


def _build_new_holding_msg(trader: Trader, new_addrs: set[str]) -> str:
    lines = []
    for h in trader.top_holdings:
        if h.token_address in new_addrs:
            lines.append(f"  • `{h.token_address}` — val: {_fmt_usd(h.value_usd)} | pnl: {_fmt_usd(h.pnl_usd)}")

    return (
        f"🆕 *Top trader thêm holding mới — Fomo*\n\n"
        f"*#{trader.rank} [{trader.display_name}]({_fomo_profile_url(trader.user_handle)})*\n"
        f"💰 PnL: {_fmt_usd(trader.total_pnl)}\n"
        f"🪙 Token mới:\n" + "\n".join(lines)
    )


async def fomo_leaderboard_alert_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chats = get_fomo_subscribed_chats()
    if not chats:
        return

    client = get_fomo_client()
    if client is None:
        return

    try:
        traders = await client.get_leaderboard(limit=_TOP_N)
    except FomoTokenExpiredError:
        logger.warning("fomo.leaderboard_alert.token_expired")
        for chat_id in chats:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ *Fomo Alert*: Token hết hạn. Dùng `/fomo token <new_token>` để cập nhật.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return
    except Exception:
        logger.exception("fomo.leaderboard_alert.unexpected_error")
        return

    if not traders:
        return

    messages: list[str] = []

    for trader in traders:
        old_rank = _last_ranks.get(trader.id)

        # New entry into top N
        if old_rank is None or old_rank > _TOP_N:
            if _last_ranks:  # skip on first run (no baseline yet)
                messages.append(_build_new_entry_msg(trader))
        elif old_rank - trader.rank >= _RANK_JUMP_THRESHOLD:
            messages.append(_build_rank_jump_msg(trader, old_rank))

        # New token in topHoldings (only for top 5)
        if trader.rank <= 5 and _last_holdings:
            prev_holdings = _last_holdings.get(trader.id, set())
            current_addrs = {h.token_address for h in trader.top_holdings}
            new_addrs = current_addrs - prev_holdings
            if new_addrs:
                messages.append(_build_new_holding_msg(trader, new_addrs))

    # Update snapshots
    _last_ranks.clear()
    _last_holdings.clear()
    for trader in traders:
        _last_ranks[trader.id] = trader.rank
        _last_holdings[trader.id] = {h.token_address for h in trader.top_holdings}

    for msg in messages:
        for chat_id in chats:
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            except Exception:
                logger.exception("fomo.leaderboard_alert.send_failed", extra={"chat_id": chat_id})
