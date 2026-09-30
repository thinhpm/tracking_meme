import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.jobs.radar_alert_dispatcher import radar_alert_dispatcher_job


@pytest.mark.asyncio
async def test_dispatcher_sends_alert_for_qualified_signals():
    signal_doc = {
        "_id": "signal_1",
        "token_mint": "7xKXtg2CW87d97TXJSDmbD5jBk4jhPmpump",
        "token_name": "Pepe 2.0",
        "token_symbol": "PEPE2",
        "chain": "solana",
        "score": 86,
        "tier": "A_GRADE_SNIPER",
        "status": "qualified",
        "dispatched": False,
        "liquidity_usd": 84500.0,
        "market_cap_usd": 210000.0,
        "age_seconds": 240,
        "conviction": 2.14,
        "wallets_detail": [],
    }

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[signal_doc])
    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_cursor
    mock_collection.update_one = AsyncMock()
    mock_db.__getitem__.return_value = mock_collection

    mock_settings = MagicMock()
    mock_settings.admin_chat_id = "123456"

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    with patch("app.jobs.radar_alert_dispatcher.get_db", return_value=mock_db), \
         patch("app.jobs.radar_alert_dispatcher.get_settings", return_value=mock_settings), \
         patch("app.jobs.radar_alert_dispatcher.get_fomo_subscribed_chats", return_value={123456}):

        await radar_alert_dispatcher_job(context)

        # Verified message sent
        context.bot.send_message.assert_called_once()
        call_kwargs = context.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 123456
        assert "PEPE2" in call_kwargs["text"]
        assert call_kwargs["reply_markup"] is not None

        # Verified document marked as dispatched
        mock_collection.update_one.assert_called_once()
        filter_arg, update_arg = mock_collection.update_one.call_args[0]
        assert filter_arg == {"_id": "signal_1"}
        assert update_arg["$set"]["dispatched"] is True


@pytest.mark.asyncio
async def test_dispatcher_skips_when_no_signals():
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_cursor
    mock_db.__getitem__.return_value = mock_collection

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    with patch("app.jobs.radar_alert_dispatcher.get_db", return_value=mock_db), \
         patch("app.jobs.radar_alert_dispatcher.get_fomo_subscribed_chats", return_value={123456}):

        await radar_alert_dispatcher_job(context)
        context.bot.send_message.assert_not_called()
