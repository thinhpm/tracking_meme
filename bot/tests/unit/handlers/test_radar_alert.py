import pytest
from telegram import InlineKeyboardMarkup
from app.handlers.radar_alert import RadarAlertFormatter


def test_format_radar_alert():
    signal_doc = {
        "token_mint": "7xKXtg2CW87d97TXJSDmbD5jBk4jhPmpump",
        "token_name": "Pepe 2.0",
        "token_symbol": "PEPE2",
        "chain": "solana",
        "score": 86,
        "tier": "A_GRADE_SNIPER",
        "liquidity_usd": 84500.0,
        "market_cap_usd": 210000.0,
        "age_seconds": 240,
        "conviction": 2.14,
        "wallets_detail": [
            {"handle": "sol_whale", "score": 91, "amount_usd": 4500.0, "time_ago": "3m ago"},
            {"handle": "alpha_trader", "score": 84, "amount_usd": 3200.0, "time_ago": "2m ago"},
        ],
        "security": {
            "mint_auth": "Revoked ✅",
            "freeze_auth": "Revoked ✅",
            "lp_status": "100% Burned 🔥",
            "top_10_share": "18.2% ✅",
            "sell_tax": "0% Tax ✅",
        },
        "components": {
            "smart_money": 90.0,
            "momentum": 86.0,
            "safety": 100.0,
            "liquidity": 80.0,
            "social": 55.0,
        },
    }

    formatter = RadarAlertFormatter()
    text, reply_markup = formatter.format_alert(signal_doc)

    assert "🚨 *SMART MONEY CONSENSUS DETECTED*" in text
    assert "Score: *86/100*" in text
    assert "PEPE2" in text
    assert "`7xKXtg2CW87d97TXJSDmbD5jBk4jhPmpump`" in text
    assert "$84,500" in text
    assert "sol_whale" in text
    assert "2.14" in text

    # Verify buttons
    assert isinstance(reply_markup, InlineKeyboardMarkup)
    buttons = [b for row in reply_markup.inline_keyboard for b in row]
    assert len(buttons) >= 2
    assert any("DexScreener" in b.text for b in buttons)
    assert any("dexscreener.com/solana/7xKXtg2CW87d97TXJSDmbD5jBk4jhPmpump" in b.url for b in buttons)
