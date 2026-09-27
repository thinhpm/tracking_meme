"""Poll tracked wallets for new transactions and notify."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram.ext import ContextTypes

from app.handlers.wallet import get_zerion_client, get_tracked_wallets, _short_addr, _fmt_usd, _fmt_time
from app.services.zerion_client import WalletTransaction

logger = logging.getLogger(__name__)

# address → set of tx hashes seen
_last_tx_hashes: dict[str, set[str]] = {}
_initialized = False


def _build_notify_msg(address: str, tx: WalletTransaction) -> str:
    op = tx.operation_type
    short = _short_addr(address)

    if op == "trade":
        sold = [t for t in tx.transfers if t.direction == "out"]
        bought = [t for t in tx.transfers if t.direction == "in"]
        if sold and bought:
            s = sold[0]; b = bought[0]
            s_ca = f"`{s.contract_address}`" if s.contract_address else f"*{s.symbol}*"
            b_ca = f"`{b.contract_address}`" if b.contract_address else f"*{b.symbol}*"
            return (
                f"🔔 *Trade mới* — `{short}`\n\n"
                f"🔄 Swap\n"
                f"  📤 Bán *{s.symbol}* {_fmt_usd(s.value_usd)}\n"
                f"     CA: {s_ca}\n"
                f"  📥 Mua *{b.symbol}* {_fmt_usd(b.value_usd)}\n"
                f"     CA: {b_ca}\n"
                f"🌐 Chain: {tx.chain_id}\n"
                f"⏰ {_fmt_time(tx.mined_at)}"
            )
    elif op == "receive":
        for t in tx.transfers:
            ca = f"`{t.contract_address}`" if t.contract_address else f"*{t.symbol}*"
            return (
                f"🔔 *Nhận token* — `{short}`\n\n"
                f"📥 *{t.symbol}* {_fmt_usd(t.value_usd)}\n"
                f"     CA: {ca}\n"
                f"🌐 Chain: {t.chain_id or tx.chain_id}\n"
                f"⏰ {_fmt_time(tx.mined_at)}"
            )
    elif op == "send":
        for t in tx.transfers:
            ca = f"`{t.contract_address}`" if t.contract_address else f"*{t.symbol}*"
            return (
                f"🔔 *Gửi token* — `{short}`\n\n"
                f"📤 *{t.symbol}* {_fmt_usd(t.value_usd)}\n"
                f"     CA: {ca}\n"
                f"🌐 Chain: {t.chain_id or tx.chain_id}\n"
                f"⏰ {_fmt_time(tx.mined_at)}"
            )

    return f"🔔 *{op}* — `{short}` — {_fmt_time(tx.mined_at)}"


async def wallet_tracking_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    global _initialized

    tracked = get_tracked_wallets()
    # Flatten: all unique addresses across all chats
    all_addresses: dict[str, set[int]] = {}  # address → set of chat_ids watching it
    for chat_id, addrs in tracked.items():
        for addr in addrs:
            all_addresses.setdefault(addr, set()).add(chat_id)

    if not all_addresses:
        return

    client = get_zerion_client()
    if client is None:
        return

    new_notifications: list[tuple[set[int], str]] = []  # (chat_ids, message)

    for address, chat_ids in all_addresses.items():
        try:
            txs = await client.get_transactions(address, limit=10)
        except Exception:
            logger.exception("wallet_tracking.fetch_error", extra={"address": address})
            continue

        current_hashes = {tx.tx_hash for tx in txs if tx.tx_hash}
        prev_hashes = _last_tx_hashes.get(address, set())

        if not _initialized:
            _last_tx_hashes[address] = current_hashes
            continue

        new_hashes = current_hashes - prev_hashes
        if new_hashes:
            for tx in txs:
                if tx.tx_hash in new_hashes:
                    msg = _build_notify_msg(address, tx)
                    new_notifications.append((chat_ids, msg))

        _last_tx_hashes[address] = current_hashes

    if not _initialized:
        _initialized = True
        logger.info("wallet_tracking.initialized", extra={"wallets": len(all_addresses)})
        return

    for chat_ids, msg in new_notifications:
        for chat_id in chat_ids:
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            except Exception:
                logger.exception("wallet_tracking.send_failed", extra={"chat_id": chat_id})
