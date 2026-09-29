import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.wallet_resolver import WalletResolver, FomoSwap, ResolutionResult


@pytest.fixture
def mock_rpc_client():
    client = MagicMock()
    return client


@pytest.fixture
def mock_db():
    db = MagicMock()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    db.__getitem__.return_value = collection
    return db


@pytest.mark.asyncio
async def test_resolve_trader_wallet_success_100_percent(mock_rpc_client, mock_db):
    swaps = [
        FomoSwap(token_address="TokenA", timestamp=1000, amount_usd=500.0),
        FomoSwap(token_address="TokenB", timestamp=2000, amount_usd=1200.0),
        FomoSwap(token_address="TokenC", timestamp=3000, amount_usd=800.0),
    ]

    # W1 appears in all 3 swaps, W2 only in swap 1, W3 only in swap 2 and 3
    mock_rpc_client.get_candidate_signers = AsyncMock(side_effect=[
        ["W1", "W2"],
        ["W1", "W3"],
        ["W1", "W3", "W4"],
    ])

    resolver = WalletResolver(rpc_client=mock_rpc_client, db=mock_db)
    result = await resolver.resolve_trader_wallet(
        trader_handle="legend_trader",
        fomo_swaps=swaps,
        chain="solana",
    )

    assert isinstance(result, ResolutionResult)
    assert result.resolved_wallet == "W1"
    assert result.confidence == 1.0
    assert result.candidate_matches["W1"] == 3
    assert result.candidate_matches["W3"] == 2

    # Verify MongoDB upsert
    mock_db["tracked_wallets"].update_one.assert_called_once()
    filter_arg, update_arg = mock_db["tracked_wallets"].update_one.call_args[0]
    assert filter_arg == {"address": "W1", "chain": "solana"}
    assert update_arg["$set"]["source"] == "fomo_resolved"
    assert update_arg["$set"]["fomo_handle"] == "legend_trader"


@pytest.mark.asyncio
async def test_resolve_trader_wallet_rejects_low_confidence(mock_rpc_client, mock_db):
    swaps = [
        FomoSwap(token_address="TokenA", timestamp=1000, amount_usd=500.0),
        FomoSwap(token_address="TokenB", timestamp=2000, amount_usd=1200.0),
        FomoSwap(token_address="TokenC", timestamp=3000, amount_usd=800.0),
    ]

    # Top candidate W1 appears in 2 of 3 swaps (confidence 0.67 < 0.95)
    mock_rpc_client.get_candidate_signers = AsyncMock(side_effect=[
        ["W1", "W2"],
        ["W1", "W3"],
        ["W4", "W5"],
    ])

    resolver = WalletResolver(rpc_client=mock_rpc_client, db=mock_db, min_confidence=0.95)
    result = await resolver.resolve_trader_wallet(
        trader_handle="noisy_trader",
        fomo_swaps=swaps,
        chain="solana",
    )

    assert result.resolved_wallet is None
    assert pytest.approx(result.confidence, 0.01) == 0.67
    mock_db["tracked_wallets"].update_one.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_trader_wallet_empty_swaps(mock_rpc_client, mock_db):
    resolver = WalletResolver(rpc_client=mock_rpc_client, db=mock_db)
    result = await resolver.resolve_trader_wallet(
        trader_handle="empty_trader",
        fomo_swaps=[],
        chain="solana",
    )
    assert result.resolved_wallet is None
    assert result.confidence == 0.0
