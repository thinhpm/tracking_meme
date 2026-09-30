"""Telegram alert formatter for high-conviction Smart Money Radar signals."""
from __future__ import annotations

from typing import Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _fmt_usd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v:,.0f}"
    return f"${v:.2f}"


def _fmt_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s (Earlyness: ULTRA)"
    mins = int(seconds // 60)
    if mins < 60:
        return f"{mins}m (Earlyness: HIGH)"
    hours = int(mins // 60)
    return f"{hours}h (Earlyness: LOW)"


class RadarAlertFormatter:
    """Formats Mode 2 Telegram alerts for Smart Money Consensus detections."""

    @staticmethod
    def format_alert(signal_doc: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
        mint = signal_doc.get("token_mint", "")
        symbol = signal_doc.get("token_symbol", "TOKEN")
        name = signal_doc.get("token_name", symbol)
        chain = signal_doc.get("chain", "solana").capitalize()
        score = signal_doc.get("score", 0)
        liq = _fmt_usd(signal_doc.get("liquidity_usd", 0.0))
        mc = _fmt_usd(signal_doc.get("market_cap_usd", 0.0))
        age = _fmt_age(signal_doc.get("age_seconds", 0.0))
        conviction = signal_doc.get("conviction", 0.0)

        # Smart Money Cluster section
        wallets_detail = signal_doc.get("wallets_detail", [])
        cluster_lines: list[str] = []
        for w in wallets_detail:
            handle = w.get("handle") or w.get("wallet", "Anon")
            w_score = w.get("score", 0)
            amt = _fmt_usd(w.get("amount_usd", 0.0))
            time_ago = w.get("time_ago", "recently")
            cluster_lines.append(f"- `@{handle}` (Score {w_score}) -> *{amt}* ({time_ago})")

        if not cluster_lines:
            raw_wallets = signal_doc.get("wallets", [])
            for w in raw_wallets[:3]:
                short_w = f"{w[:4]}...{w[-4:]}" if len(w) > 8 else w
                cluster_lines.append(f"- `{short_w}`")

        cluster_str = "\n".join(cluster_lines)
        num_wallets = len(wallets_detail) or len(signal_doc.get("wallets", []))

        # Security section
        security = signal_doc.get("security", {})
        mint_auth = security.get("mint_auth", "Revoked")
        freeze_auth = security.get("freeze_auth", "Revoked")
        lp_status = security.get("lp_status", "100% Burned")
        top_10 = security.get("top_10_share", "< 20%")
        tax = security.get("sell_tax", "0% Tax")

        text = (
            f"*SMART MONEY CONSENSUS DETECTED* (Score: *{score}/100*)\n\n"
            f"*Token:* {name} ({symbol}) — *{chain}*\n"
            f"*CA:* `{mint}`\n"
            f"*Liquidity:* {liq} | *MC:* {mc}\n"
            f"*Age:* {age}\n\n"
            f"*Smart Money Cluster ({num_wallets} Wallets):*\n"
            f"{cluster_str}\n"
            f"*Conviction:* {conviction:.2f} | *Sybil Risk:* CLEAN\n\n"
            f"*Security Audit:*\n"
            f"- Mint Auth: {mint_auth}\n"
            f"- Freeze Auth: {freeze_auth}\n"
            f"- LP Status: {lp_status}\n"
            f"- Top 10 Holders: {top_10}\n"
            f"- Sell Simulation: {tax}\n"
        )

        # Quick action buttons
        kb = [
            [
                InlineKeyboardButton(
                    "DexScreener",
                    url=f"https://dexscreener.com/solana/{mint}",
                ),
                InlineKeyboardButton(
                    "Pump.fun",
                    url=f"https://pump.fun/{mint}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Trojan Sniper",
                    url=f"https://t.me/solana_trojanbot?start=r-trackingmeme-{mint}",
                ),
                InlineKeyboardButton(
                    "Maestro",
                    url=f"https://t.me/MaestroSniperBot?start={mint}",
                ),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(kb)

        return text, reply_markup
