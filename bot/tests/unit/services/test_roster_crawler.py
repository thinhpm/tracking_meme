import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.fomo_client import Trader, FollowedUser
from app.services.roster_crawler import RosterCrawler, compute_expanded_wallet_score


@pytest.fixture
def mock_fomo_client():
    client = MagicMock()
    return client


@pytest.fixture
def mock_db():
    db = MagicMock()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    db.__getitem__.return_value = collection
    return db


def test_compute_expanded_wallet_score():
    score = compute_expanded_wallet_score(
        pnl24h=15000.0,
        total_volume=2000000.0,
        num_trades=100,
        peer_endorsement_count=2,
        badge="top_100_badge",
    )
    # baseline 50 + 20 (endorsements) + 15 (top 100) + 10 (volume) + 10 (pnl) = 105 -> capped at 100
    assert score == 100.0

    score_low = compute_expanded_wallet_score(
        pnl24h=-500.0,
        total_volume=5000.0,
        num_trades=5,
        peer_endorsement_count=0,
        badge=None,
    )
    # baseline 50 + 0 + 0 + 0 - 5 = 45.0
    assert score_low == 45.0


@pytest.mark.asyncio
async def test_crawl_top_traders_network(mock_fomo_client, mock_db):
    # Setup 2 top traders
    mock_fomo_client.get_leaderboard = AsyncMock(return_value=[
        Trader(
            id="t1",
            user_handle="whale1",
            display_name="Whale 1",
            address="SolWhale1",
            evm_address="0xWhale1",
            total_pnl=100000.0,
            num_trades=500,
            total_volume=5000000.0,
            followers=1000,
            top_holdings=[],
            rank=1,
        ),
        Trader(
            id="t2",
            user_handle="whale2",
            display_name="Whale 2",
            address="SolWhale2",
            evm_address="0xWhale2",
            total_pnl=80000.0,
            num_trades=300,
            total_volume=3000000.0,
            followers=800,
            top_holdings=[],
            rank=2,
        ),
    ])

    # Following networks:
    # Both whale1 and whale2 follow SolAlpha (peer endorsement = 2)
    # Only whale1 follows SolBeta (peer endorsement = 1)
    user_alpha = FollowedUser(
        id="u_alpha",
        address="SolAlphaAddress",
        evm_address="0xAlphaAddress",
        user_handle="alpha_trader",
        display_name="Alpha Trader",
        followers=200,
        following=30,
        num_trades=150,
        total_volume=1200000.0,
        pnl24h=8000.0,
        badge="top_100_badge",
        profile_picture_link=None,
    )

    user_beta = FollowedUser(
        id="u_beta",
        address="SolBetaAddress",
        evm_address="",
        user_handle="beta_trader",
        display_name="Beta Trader",
        followers=50,
        following=20,
        num_trades=40,
        total_volume=50000.0,
        pnl24h=100.0,
        badge=None,
        profile_picture_link=None,
    )

    mock_fomo_client.get_user_following_paginate = AsyncMock(side_effect=[
        [user_alpha, user_beta],  # whale1's following
        [user_alpha],             # whale2's following
    ])

    crawler = RosterCrawler(fomo_client=mock_fomo_client, db=mock_db, sleep_delay=0.0)
    summary = await crawler.crawl_top_traders_network(top_n=2)

    assert summary["top_traders_scanned"] == 2
    assert summary["unique_followed_users"] == 2
    assert summary["solana_wallets_upserted"] >= 2

    # Check that update_one was called for SolAlphaAddress with peer_endorsement_count = 2
    calls = mock_db["tracked_wallets"].update_one.call_args_list
    alpha_calls = [
        c for c in calls if c[0][0].get("address") == "SolAlphaAddress"
    ]
    assert len(alpha_calls) >= 1
    alpha_update = alpha_calls[-1][0][1]["$set"]
    assert alpha_update["peer_endorsement_count"] == 2
    assert "whale1" in alpha_update["endorsed_by"]
    assert "whale2" in alpha_update["endorsed_by"]
    assert alpha_update["tier"] == "tier_2"
