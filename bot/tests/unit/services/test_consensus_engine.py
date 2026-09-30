import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from app.services.consensus_engine import (
    ConsensusEngine,
    WalletBuyEvent,
    ConsensusSignal,
    compute_earlyness_factor,
)


def test_compute_earlyness_factor():
    # 0s -> 1.0 / (1 + 0) = 1.0
    assert pytest.approx(compute_earlyness_factor(age_seconds=0), 0.001) == 1.0
    # 3600s (1h) -> 1.0 / (1 + 1) = 0.50
    assert pytest.approx(compute_earlyness_factor(age_seconds=3600), 0.001) == 0.50
    # 7200s (2h) -> 1.0 / (1 + 2) = 0.333
    assert pytest.approx(compute_earlyness_factor(age_seconds=7200), 0.001) == 0.3333
    # 36000s (10h) -> 1.0 / (1 + 10) = 0.0909
    assert pytest.approx(compute_earlyness_factor(age_seconds=36000), 0.001) == 0.0909
    # Undated (None) -> fallback to 0.50 (1 hour equivalent), never 1.0
    assert pytest.approx(compute_earlyness_factor(age_seconds=None), 0.001) == 0.50



@pytest.mark.asyncio
async def test_single_wallet_buy_no_consensus():
    engine = ConsensusEngine(window_seconds=60)
    now = time.time()

    event = WalletBuyEvent(
        token_mint="TokenABC",
        wallet_address="W1",
        wallet_score=90.0,
        timestamp=now,
        amount_usd=500.0,
        launch_timestamp=now - 30,
    )

    signal = await engine.add_buy(event)
    assert isinstance(signal, ConsensusSignal)
    assert signal.is_consensus is False
    assert len(signal.wallets) == 1
    assert pytest.approx(signal.conviction, 0.01) == 0.81  # 0.9^2
    assert pytest.approx(signal.earlyness, 0.01) == 0.992
    assert pytest.approx(signal.heat, 0.01) == 0.803


@pytest.mark.asyncio
async def test_two_wallets_trigger_consensus_cluster():
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.update_one = AsyncMock()
    mock_db.__getitem__.return_value = mock_collection

    engine = ConsensusEngine(db=mock_db, window_seconds=60)
    now = time.time()

    # Buy 1: Wallet W1 (score 90)
    await engine.add_buy(WalletBuyEvent(
        token_mint="TokenABC",
        wallet_address="W1",
        wallet_score=90.0,
        timestamp=now,
        amount_usd=500.0,
        launch_timestamp=now - 30,
    ))

    # Buy 2: Wallet W2 (score 80) within 30s
    signal = await engine.add_buy(WalletBuyEvent(
        token_mint="TokenABC",
        wallet_address="W2",
        wallet_score=80.0,
        timestamp=now + 20,
        amount_usd=800.0,
        launch_timestamp=now - 30,
    ))

    # Conviction = 0.9^2 + 0.8^2 = 0.81 + 0.64 = 1.45 >= 1.3
    assert signal.is_consensus is True
    assert set(signal.wallets) == {"W1", "W2"}
    assert pytest.approx(signal.conviction, 0.01) == 1.45
    assert pytest.approx(signal.earlyness, 0.01) == 0.986
    assert pytest.approx(signal.heat, 0.01) == 1.43

    # Check MongoDB token_signals upsert
    mock_db["token_signals"].update_one.assert_called_once()
    filter_arg, update_arg = mock_db["token_signals"].update_one.call_args[0]
    assert filter_arg == {"token_mint": "TokenABC"}
    assert update_arg["$set"]["is_consensus"] is True


@pytest.mark.asyncio
async def test_window_expiry_removes_old_buys():
    engine = ConsensusEngine(window_seconds=60)
    now = time.time()

    # Buy 1 at t=0
    await engine.add_buy(WalletBuyEvent(
        token_mint="TokenABC",
        wallet_address="W1",
        wallet_score=90.0,
        timestamp=now,
        amount_usd=500.0,
    ))

    # Buy 2 at t=70 (> 60s later)
    signal = await engine.add_buy(WalletBuyEvent(
        token_mint="TokenABC",
        wallet_address="W2",
        wallet_score=80.0,
        timestamp=now + 70,
        amount_usd=500.0,
    ))

    # W1 expired from window, so only W2 is in the window
    assert len(signal.wallets) == 1
    assert signal.wallets == ["W2"]
    assert signal.is_consensus is False
