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
    assert pytest.approx(result.max_funder_share, 0.01) == 0.33
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
