"""Fomo.family leaderboard alert handler.

Commands:
  /fomo               — show status
  /fomo on            — subscribe this chat
  /fomo off           — unsubscribe this chat
  /fomo token <jwt>   — update Privy auth token
  /fomo top           — show current top 10 leaderboard
  /fomo watching      — show accounts being followed
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.services.fomo_client import FomoClient, FomoTokenExpiredError, FollowedTrader

logger = logging.getLogger(__name__)

_subscribed_chats: set[int] = set()
_fomo_client: FomoClient | None = None


def get_fomo_subscribed_chats() -> set[int]:
    return _subscribed_chats.copy()


def get_fomo_client() -> FomoClient | None:
    return _fomo_client


def _fmt_usd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


async def fomo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _fomo_client

    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    args = context.args or []

    if not args:
        subscribed = chat_id in _subscribed_chats
        token_ok = _fomo_client is not None and not _fomo_client.is_token_expired()
        status_sub = "bật ✅" if subscribed else "tắt ❌"
        status_token = "hợp lệ ✅" if token_ok else "hết hạn / chưa set ❌"
        await update.message.reply_text(
            f"📊 *Fomo Leaderboard Alert*\n\n"
            f"• Trạng thái: {status_sub}\n"
            f"• Token: {status_token}\n\n"
            f"`/fomo on` — bật alert\n"
            f"`/fomo off` — tắt alert\n"
            f"`/fomo token <jwt>` — cập nhật token\n"
            f"`/fomo top` — xem leaderboard ngay",
            parse_mode="Markdown",
        )
        return

    action = args[0].lower()

    if action == "on":
        _subscribed_chats.add(chat_id)
        logger.info("fomo.subscribed", extra={"chat_id": chat_id})
        if _fomo_client is None or _fomo_client.is_token_expired():
            await update.message.reply_text(
                "✅ Đã bật Fomo Alert.\n⚠️ Cần set token: `/fomo token <jwt>`",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "✅ *Fomo Leaderboard Alert bật!*\n"
                "Bot sẽ thông báo khi top trader thay đổi.",
                parse_mode="Markdown",
            )

    elif action == "off":
        _subscribed_chats.discard(chat_id)
        logger.info("fomo.unsubscribed", extra={"chat_id": chat_id})
        await update.message.reply_text("❌ Đã tắt Fomo Alert.")

    elif action == "token":
        if len(args) < 2:
            await update.message.reply_text(
                "Cú pháp: `/fomo token <jwt_token>`", parse_mode="Markdown"
            )
            return
        new_token = args[1]
        _fomo_client = FomoClient(new_token)
        if _fomo_client.is_token_expired():
            await update.message.reply_text(
                "⚠️ Token đã hết hạn. Vui lòng lấy token mới từ fomo.family."
            )
        else:
            logger.info("fomo.token_updated")
            await update.message.reply_text("✅ Token Fomo đã cập nhật thành công.")

    elif action == "top":
        if _fomo_client is None:
            await update.message.reply_text(
                "⚠️ Chưa có token. Dùng `/fomo token <jwt>`", parse_mode="Markdown"
            )
            return
        await update.message.reply_text("🔍 Đang tải leaderboard...")
        try:
            traders = await _fomo_client.get_leaderboard(limit=10)
        except FomoTokenExpiredError:
            await update.message.reply_text(
                "⚠️ Token hết hạn. Dùng `/fomo token <jwt>` để cập nhật.",
                parse_mode="Markdown",
            )
            return
        except Exception:
            logger.exception("fomo.top_command.error")
            await update.message.reply_text("❌ Lỗi khi tải leaderboard.")
            return

        if not traders:
            await update.message.reply_text("Không có dữ liệu.")
            return

        lines = ["🏆 *Fomo Top 10 Leaderboard*\n"]
        for t in traders:
            holdings_str = ""
            if t.top_holdings:
                addrs = [h.token_address[:8] + "…" for h in t.top_holdings[:2]]
                holdings_str = f" | 🪙 {', '.join(f'`{a}`' for a in addrs)}"
            profile = f"https://fomo.family/{t.user_handle}"
            lines.append(
                f"*#{t.rank}* [{t.display_name}]({profile})\n"
                f"  💰 {_fmt_usd(t.total_pnl)} | 📊 {t.num_trades:,} trades{holdings_str}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif action == "watching":
        if _fomo_client is None:
            await update.message.reply_text(
                "⚠️ Chưa có token. Dùng `/fomo token <jwt>`", parse_mode="Markdown"
            )
            return
        await update.message.reply_text("🔍 Đang tải danh sách following...")
        try:
            following_list: list[FollowedTrader] = await _fomo_client.get_following()
        except FomoTokenExpiredError:
            await update.message.reply_text(
                "⚠️ Token hết hạn. Dùng `/fomo token <jwt>` để cập nhật.",
                parse_mode="Markdown",
            )
            return
        except Exception:
            logger.exception("fomo.watching_command.error")
            await update.message.reply_text("❌ Lỗi khi tải following.")
            return

        if not following_list:
            await update.message.reply_text("Chưa follow ai trên fomo.family.")
            return

        lines = [f"👀 *Đang following ({len(following_list)} người)*\n"]
        for tr in following_list:
            profile = f"https://fomo.family/{tr.user_handle}"
            lines.append(
                f"• [{tr.display_name}]({profile})\n"
                f"  💰 {_fmt_usd(tr.total_pnl)} PnL | 📊 {tr.num_trades:,} trades | 👥 {tr.followers:,} followers"
            )
        lines.append("\n_Bot sẽ notify khi họ giao dịch._")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    else:
        await update.message.reply_text(
            "Cú pháp: `/fomo on|off|token|top|watching`", parse_mode="Markdown"
        )
