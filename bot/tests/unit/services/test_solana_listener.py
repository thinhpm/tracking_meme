import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.chain.solana_listener import (
    SolanaEventListener,
    SolanaSwapEvent,
    parse_pump_fun_log,
    parse_raydium_log,
    parse_solana_log_notification,
)


def test_parse_pump_fun_buy_log():
    logs = [
        "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]",
        "Program log: Instruction: Buy",
        "Program data: user=UserWallet111111111111111111111111111111111 mint=TokenMint111111111111111111111111111111111 sol_amount=1000000000 token_amount=5000000",
        "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success",
    ]
    event = parse_pump_fun_log(logs, signature="sig_pump_1")
    assert event is not None
    assert event.signature == "sig_pump_1"
    assert event.dex == "pump_fun"
    assert event.is_buy is True
    assert event.user_wallet == "UserWallet111111111111111111111111111111111"
    assert event.mint == "TokenMint111111111111111111111111111111111"


def test_parse_pump_fun_sell_log():
    logs = [
        "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]",
        "Program log: Instruction: Sell",
        "Program data: user=UserWallet222222222222222222222222222222222 mint=TokenMint222222222222222222222222222222222 sol_amount=500000000 token_amount=2000000",
        "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success",
    ]
    event = parse_pump_fun_log(logs, signature="sig_pump_2")
    assert event is not None
    assert event.dex == "pump_fun"
    assert event.is_buy is False
    assert event.user_wallet == "UserWallet222222222222222222222222222222222"


def test_parse_raydium_swap_log():
    logs = [
        "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 invoke [1]",
        "Program log: Instruction: SwapBaseIn",
        "Program log: ray_log: user=RayUser11111111111111111111111111111111111 mint=RayMint11111111111111111111111111111111111 in_amount=1000000 out_amount=50000000",
        "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 success",
    ]
    event = parse_raydium_log(logs, signature="sig_ray_1")
    assert event is not None
    assert event.signature == "sig_ray_1"
    assert event.dex == "raydium"
    assert event.user_wallet == "RayUser11111111111111111111111111111111111"
    assert event.mint == "RayMint11111111111111111111111111111111111"
    assert event.is_buy is True


@pytest.mark.asyncio
async def test_solana_listener_filters_tracked_wallets():
    tracked = {"TrackedUser123"}
    callback = AsyncMock()

    listener = SolanaEventListener(
        ws_url="wss://mock-solana-ws",
        tracked_wallets=tracked,
        on_swap_callback=callback,
    )

    # 1. Event from UNTRACKED wallet -> ignored
    untracked_notif = {
        "signature": "sig_1",
        "err": None,
        "logs": [
            "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]",
            "Program log: Instruction: Buy",
            "Program data: user=OtherUser999 mint=MintABC sol_amount=1000",
            "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success",
        ],
    }
    await listener.handle_log_notification(untracked_notif)
    callback.assert_not_called()

    # 2. Event from TRACKED wallet -> triggers callback
    tracked_notif = {
        "signature": "sig_2",
        "err": None,
        "logs": [
            "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]",
            "Program log: Instruction: Buy",
            "Program data: user=TrackedUser123 mint=MintABC sol_amount=1000",
            "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success",
        ],
    }
    await listener.handle_log_notification(tracked_notif)
    callback.assert_called_once()
    event_arg = callback.call_args[0][0]
    assert isinstance(event_arg, SolanaSwapEvent)
    assert event_arg.user_wallet == "TrackedUser123"
    assert event_arg.mint == "MintABC"


@pytest.mark.asyncio
async def test_solana_listener_reconnection_backoff():
    listener = SolanaEventListener(
        ws_url="wss://mock-solana-ws",
        max_reconnect_attempts=3,
        initial_backoff_seconds=0.01,
        backoff_multiplier=2.0,
    )

    with patch("websockets.connect", side_effect=Exception("Connection failed")):
        # Should attempt 3 times and backoff exponentially then stop
        await listener.connect_and_listen()

    assert listener.reconnect_attempts == 3


def test_solana_listener_add_wallet_and_stop():
    listener = SolanaEventListener(ws_url="wss://mock")
    assert listener.is_tracked("Wallet1") is False
    listener.add_tracked_wallet("Wallet1")
    assert listener.is_tracked("Wallet1") is True

    listener.stop()
    assert listener._running is False


def test_parse_solana_log_notification_empty():
    assert parse_solana_log_notification({}) is None
    assert parse_solana_log_notification({"logs": []}) is None
    assert parse_solana_log_notification({"logs": ["random log line"]}) is None
