from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.handlers.fomo import fomo_command, radar_command


@pytest.mark.asyncio
async def test_fomo_radar_command_triggers_real_scan_when_no_signals():
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = ["radar"]

    mock_db = MagicMock()
    mock_coll = MagicMock()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    mock_coll.find.return_value = cursor
    mock_db.__getitem__.return_value = mock_coll

    scanned_signal = {
        "_id": "scanned_mint_999",
        "token_mint": "scanned_mint_999",
        "token_symbol": "SCAN",
        "token_name": "ScannedToken",
        "chain": "solana",
        "score": 88.0,
        "liquidity_usd": 12000.0,
        "market_cap_usd": 80000.0,
        "age_seconds": 90.0,
        "conviction": 1.70,
        "wallets_detail": [
            {"handle": "Whale1", "score": 92, "amount_usd": 3000, "time_ago": "1m ago"}
        ],
    }

    with patch("app.db.mongo.get_db", return_value=mock_db), \
         patch("app.services.radar_scanner.scan_and_generate_radar_signal", return_value=scanned_signal) as mock_scan:
        await fomo_command(update, ctx)

    mock_scan.assert_called_once()
    assert update.message.reply_text.call_count >= 2
    # Verify alert was formatted with scanned token
    last_call = update.message.reply_text.call_args_list[-1]
    assert "scanned_mint_999" in last_call[1]["text"]


@pytest.mark.asyncio
async def test_radar_command_with_signal():
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()

    mock_db = MagicMock()
    mock_coll = MagicMock()
    sample_signal = {
        "_id": "token_mint_123",
        "token_mint": "token_mint_123",
        "token_symbol": "MOON",
        "token_name": "MoonRocket",
        "chain": "solana",
        "score": 92.5,
        "liquidity_usd": 15000.0,
        "market_cap_usd": 150000.0,
        "age_seconds": 120.0,
        "conviction": 1.85,
        "wallets_detail": [
            {"handle": "0xWhale", "score": 95, "amount_usd": 5000, "time_ago": "2m ago"}
        ],
    }
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[sample_signal])
    mock_coll.find.return_value = cursor
    mock_db.__getitem__.return_value = mock_coll

    with patch("app.db.mongo.get_db", return_value=mock_db):
        await radar_command(update, ctx)

    assert update.message.reply_text.call_count == 2
    header_call = update.message.reply_text.call_args_list[0][0][0]
    alert_call = update.message.reply_text.call_args_list[1][1]
    assert "SMART MONEY CONSENSUS RADAR" in header_call
    assert "token_mint_123" in alert_call["text"]


@pytest.mark.asyncio
async def test_fomo_radar_command_force_scan():
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = ["radar", "scan"]

    mock_db = MagicMock()
    scanned_signal = {
        "_id": "force_scan_mint",
        "token_mint": "force_scan_mint",
        "token_symbol": "FORCE",
        "token_name": "ForceScanned",
        "chain": "solana",
        "score": 95.0,
        "liquidity_usd": 25000.0,
        "market_cap_usd": 120000.0,
        "age_seconds": 45.0,
        "conviction": 1.95,
        "wallets_detail": [
            {"handle": "WhaleAlpha", "score": 98, "amount_usd": 4000, "time_ago": "30s ago"}
        ],
    }

    with patch("app.db.mongo.get_db", return_value=mock_db), \
         patch("app.services.radar_scanner.scan_and_generate_radar_signal", return_value=scanned_signal) as mock_scan:
        await fomo_command(update, ctx)

    mock_scan.assert_called_once()
    assert update.message.reply_text.call_count >= 2
    last_call = update.message.reply_text.call_args_list[-1]
    assert "force_scan_mint" in last_call[1]["text"]
