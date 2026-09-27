"""Zerion wallet tracking commands.

Commands:
  /wallet <address>         — portfolio overview
  /wallet txs <address>     — last 10 trades
  /wallet track <address>   — subscribe wallet notifications
  /wallet untrack <address> — unsubscribe wallet
  /wallet list              — show tracked wallets
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from app.services.zerion_client import ZerionClient, WalletPortfolio, TokenPosition, WalletTransaction

logger = logging.getLogger(__name__)

# chat_id → set of tracked wallet addresses
_tracked_wallets: dict[int, set[str]] = {}
_zerion_client: ZerionClient | None = None


def get_zerion_client() -> ZerionClient | None:
    return _zerion_client


def get_tracked_wallets() -> dict[int, set[str]]:
    return _tracked_wallets


def _fmt_usd(v: float) -> str:
    if abs(v) >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:.2f}"


def _short_addr(addr: str) -> str:
    if len(addr) > 12:
        return f"{addr[:6]}...{addr[-4:]}"
    return addr


def _fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%m/%d %H:%M UTC")
    except Exception:
        return iso


def _is_valid_address(addr: str) -> bool:
    return addr.startswith("0x") and len(addr) == 42


def _build_portfolio_msg(p: WalletPortfolio, positions: list[TokenPosition]) -> str:
    change_sign = "+" if p.change_1d_usd >= 0 else ""
    change_pct_str = f" ({change_sign}{p.change_1d_pct:.1f}%)" if p.change_1d_pct is not None else ""

    # Top chains (max 5)
    top_chains = sorted(p.by_chain.items(), key=lambda x: x[1], reverse=True)[:5]
    chain_lines = " | ".join(f"{c}: {_fmt_usd(v)}" for c, v in top_chains)

    # Top positions (max 8)
    pos_lines = []
    for pos in positions[:8]:
        ca_str = f"\n    📋 `{pos.contract_address}`" if pos.contract_address else ""
        pos_lines.append(f"  • *{pos.symbol}* {_fmt_usd(pos.value_usd)}{ca_str}")

    lines = [
        f"💼 *Wallet* `{_short_addr(p.address)}`\n",
        f"💰 Tổng: *{_fmt_usd(p.total_usd)}*",
        f"📈 24h: {change_sign}{_fmt_usd(p.change_1d_usd)}{change_pct_str}",
        f"🌐 Chains: {chain_lines}",
    ]
    if pos_lines:
        lines.append(f"\n🪙 *Top Holdings:*")
        lines.extend(pos_lines)

    return "\n".join(lines)


def _build_tx_msg(tx: WalletTransaction) -> str:
    op = tx.operation_type
    if op == "trade":
        sold = [t for t in tx.transfers if t.direction == "out"]
        bought = [t for t in tx.transfers if t.direction == "in"]
        if sold and bought:
            s = sold[0]; b = bought[0]
            s_ca = f"`{s.contract_address}`" if s.contract_address else s.symbol
            b_ca = f"`{b.contract_address}`" if b.contract_address else b.symbol
            return (
                f"🔄 *Swap* — {_fmt_time(tx.mined_at)}\n"
                f"  📤 *{s.symbol}* {_fmt_usd(s.value_usd)}\n"
                f"     CA: {s_ca}\n"
                f"  📥 *{b.symbol}* {_fmt_usd(b.value_usd)}\n"
                f"     CA: {b_ca}"
            )
    elif op == "receive":
        for t in tx.transfers:
            ca_line = f"\n  CA: `{t.contract_address}`" if t.contract_address else ""
            return f"📥 *Nhận {t.symbol}* {_fmt_usd(t.value_usd)}{ca_line} — {_fmt_time(tx.mined_at)}"
    elif op == "send":
        for t in tx.transfers:
            ca_line = f"\n  CA: `{t.contract_address}`" if t.contract_address else ""
            return f"📤 *Gửi {t.symbol}* {_fmt_usd(t.value_usd)}{ca_line} — {_fmt_time(tx.mined_at)}"

    return f"📋 *{op}* — {_fmt_time(tx.mined_at)}"


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _zerion_client

    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    args = context.args or []

    if not args:
        await update.message.reply_text(
            "📊 *Zerion Wallet Tracker*\n\n"
            "`/wallet <addr>` — portfolio overview\n"
            "`/wallet txs <addr>` — lịch sử giao dịch\n"
            "`/wallet track <addr>` — theo dõi ví\n"
            "`/wallet untrack <addr>` — bỏ theo dõi\n"
            "`/wallet list` — danh sách đang theo dõi",
            parse_mode="Markdown",
        )
        return

    action = args[0].lower()

    # Direct address lookup
    if _is_valid_address(action):
        await _handle_portfolio(update, action)
        return

    if action == "txs":
        if len(args) < 2 or not _is_valid_address(args[1]):
            await update.message.reply_text("Cú pháp: `/wallet txs <address>`", parse_mode="Markdown")
            return
        await _handle_txs(update, args[1])

    elif action == "track":
        if len(args) < 2 or not _is_valid_address(args[1]):
            await update.message.reply_text("Cú pháp: `/wallet track <address>`", parse_mode="Markdown")
            return
        addr = args[1].lower()
        if chat_id not in _tracked_wallets:
            _tracked_wallets[chat_id] = set()
        _tracked_wallets[chat_id].add(addr)
        logger.info("wallet.tracked", extra={"chat_id": chat_id, "address": addr})
        await update.message.reply_text(
            f"✅ Đang theo dõi `{_short_addr(addr)}`\n"
            f"_Bot sẽ thông báo khi có giao dịch mới._",
            parse_mode="Markdown",
        )

    elif action == "untrack":
        if len(args) < 2 or not _is_valid_address(args[1]):
            await update.message.reply_text("Cú pháp: `/wallet untrack <address>`", parse_mode="Markdown")
            return
        addr = args[1].lower()
        wallets = _tracked_wallets.get(chat_id, set())
        wallets.discard(addr)
        await update.message.reply_text(f"❌ Đã bỏ theo dõi `{_short_addr(addr)}`", parse_mode="Markdown")

    elif action == "list":
        wallets = _tracked_wallets.get(chat_id, set())
        if not wallets:
            await update.message.reply_text("Chưa theo dõi ví nào. Dùng `/wallet track <addr>`", parse_mode="Markdown")
        else:
            lines = [f"👁 *Đang theo dõi {len(wallets)} ví:*\n"]
            for w in sorted(wallets):
                lines.append(f"  • `{w}`")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    else:
        await update.message.reply_text(
            "Cú pháp: `/wallet <addr|txs|track|untrack|list>`", parse_mode="Markdown"
        )


async def _handle_portfolio(update: Update, address: str) -> None:
    if _zerion_client is None:
        await update.message.reply_text("⚠️ Zerion chưa cấu hình.")  # type: ignore[union-attr]
        return
    msg = await update.message.reply_text("🔍 Đang tải portfolio...")  # type: ignore[union-attr]
    portfolio, positions = None, []
    try:
        import asyncio
        portfolio, positions = await asyncio.gather(
            _zerion_client.get_portfolio(address),
            _zerion_client.get_positions(address, limit=8),
        )
    except Exception:
        logger.exception("wallet.portfolio.error")
        await msg.edit_text("❌ Lỗi khi tải portfolio.")
        return

    if not portfolio:
        await msg.edit_text("❌ Không tìm thấy ví hoặc địa chỉ không hợp lệ.")
        return

    await msg.edit_text(_build_portfolio_msg(portfolio, positions), parse_mode="Markdown")


async def _handle_txs(update: Update, address: str) -> None:
    if _zerion_client is None:
        await update.message.reply_text("⚠️ Zerion chưa cấu hình.")  # type: ignore[union-attr]
        return
    msg = await update.message.reply_text("🔍 Đang tải giao dịch...")  # type: ignore[union-attr]
    try:
        txs = await _zerion_client.get_transactions(address, limit=10)
    except Exception:
        logger.exception("wallet.txs.error")
        await msg.edit_text("❌ Lỗi khi tải giao dịch.")
        return

    if not txs:
        await msg.edit_text("Không có giao dịch.")
        return

    lines = [f"📋 *Giao dịch gần nhất* `{_short_addr(address)}`\n"]
    for tx in txs:
        lines.append(_build_tx_msg(tx))

    await msg.edit_text("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)
