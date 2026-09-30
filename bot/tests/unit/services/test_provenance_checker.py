import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.provenance_checker import ProvenanceChecker, ProvenanceResult


@pytest.fixture
def mock_rpc_client():
    client = MagicMock()
    return client


@pytest.fixture
def mock_db():
    db = MagicMock()
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=None)
    collection.update_one = AsyncMock()
    db.__getitem__.return_value = collection
    return db


@pytest.mark.asyncio
async def test_cluster_sybil_detected_50_percent_share(mock_rpc_client, mock_db):
    # 4 wallets: W1 and W2 funded by CommonFunderA, W3 by FunderB, W4 by FunderC
    mock_rpc_client.get_initial_funder = AsyncMock(side_effect=lambda w: {
        "W1": "CommonFunderA",
        "W2": "CommonFunderA",
        "W3": "FunderB",
        "W4": "FunderC",
    }.get(w, w))

    checker = ProvenanceChecker(
        rpc_client=mock_rpc_client,
        db=mock_db,
        max_funder_share_threshold=0.40,
    )

    result = await checker.check_cluster_provenance(["W1", "W2", "W3", "W4"])

    assert isinstance(result, ProvenanceResult)
    assert result.is_sybil is True
    assert result.max_funder_share == 0.50  # 2/4 = 50% >= 40%
    assert result.common_funder == "CommonFunderA"
    assert result.funder_map["W1"] == "CommonFunderA"
    assert result.funder_map["W2"] == "CommonFunderA"

    # Verify db caching was performed
    assert mock_db["wallet_provenance"].update_one.call_count == 4


@pytest.mark.asyncio
async def test_cluster_independent_wallets_passes(mock_rpc_client, mock_db):
    # 3 distinct wallets with distinct funders
    mock_rpc_client.get_initial_funder = AsyncMock(side_effect=lambda w: f"Funder_{w}")

    checker = ProvenanceChecker(
        rpc_client=mock_rpc_client,
        db=mock_db,
        max_funder_share_threshold=0.40,
    )

    result = await checker.check_cluster_provenance(["W1", "W2", "W3"])

    assert result.is_sybil is False
    assert result.max_funder_share == 0.0
    assert result.common_funder is None


@pytest.mark.asyncio
async def test_db_cache_hit_avoids_rpc_query(mock_rpc_client, mock_db):
    mock_db["wallet_provenance"].find_one = AsyncMock(return_value={"_id": "W1", "funder": "CachedFunder"})

    checker = ProvenanceChecker(
        rpc_client=mock_rpc_client,
        db=mock_db,
    )

    funder = await checker.get_wallet_funder("W1")
    assert funder == "CachedFunder"
    mock_rpc_client.get_initial_funder.assert_not_called()


def test_is_dust_buy():
    from app.services.provenance_checker import is_dust_buy

    # Default floor: $10.0 when no median
    assert is_dust_buy(usd_value=5.0, median_buy_usd=None) is True
    assert is_dust_buy(usd_value=9.99, median_buy_usd=None) is True
    assert is_dust_buy(usd_value=10.0, median_buy_usd=None) is False
    assert is_dust_buy(usd_value=100.0, median_buy_usd=None) is False

    # Median scaled: median $2,000 -> 5% is $100
    assert is_dust_buy(usd_value=50.0, median_buy_usd=2000.0) is True   # < $100
    assert is_dust_buy(usd_value=99.0, median_buy_usd=2000.0) is True   # < $100
    assert is_dust_buy(usd_value=105.0, median_buy_usd=2000.0) is False # >= $100

    # Median scaled: median $50 -> 5% is $2.5, but floor is $10
    assert is_dust_buy(usd_value=8.0, median_buy_usd=50.0) is True      # < $10 floor
    assert is_dust_buy(usd_value=12.0, median_buy_usd=50.0) is False    # >= $10 floor


def test_classify_fill():
    from app.services.provenance_checker import classify_fill

    # Direct fill from router
    assert classify_fill(is_direct=True, usd_value=500.0) == "direct"

    # Dust fill
    assert classify_fill(is_direct=False, usd_value=4.0, median_buy_usd=100.0) == "dust"

    # Organic trade
    assert classify_fill(is_direct=False, usd_value=150.0, median_buy_usd=100.0) == "trade"


def test_check_seeding_wave():
    from app.services.provenance_checker import ProvenanceChecker

    checker = ProvenanceChecker()
    mint = "ScamMeme123"

    # 1st dust buy -> no wave
    is_seeded, reason = checker.record_and_check_wave(mint, wallet="W1", kind="dust", timestamp=100.0)
    assert is_seeded is False

    # 2nd dust buy to another wallet -> no wave
    is_seeded, reason = checker.record_and_check_wave(mint, wallet="W2", kind="direct", timestamp=105.0)
    assert is_seeded is False

    # Repeat wallet W1 -> still only 2 distinct wallets -> no wave
    is_seeded, reason = checker.record_and_check_wave(mint, wallet="W1", kind="dust", timestamp=110.0)
    assert is_seeded is False

    # 3rd distinct wallet W3 receives dust -> WAVE DETECTED!
    is_seeded, reason = checker.record_and_check_wave(mint, wallet="W3", kind="dust", timestamp=115.0)
    assert is_seeded is True
    assert "SEEDED_WAVE" in reason

