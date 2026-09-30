import pytest
import respx
import httpx
from app.services.fomo_client import (
    FomoClient,
    FomoTokenProvider,
    FollowedUser,
    FollowedTrader,
    TradeActivity,
    Trader,
    FomoTokenExpiredError,
)


@pytest.fixture
def fomo_client():
    provider = FomoTokenProvider(fallback_token="header.eyJleHAiOjE5OTk5OTk5OTl9.sig")
    return FomoClient(provider)


@pytest.mark.asyncio
@respx.mock
async def test_get_user_following_paginate_success(fomo_client):
    user_id = "85fb7b04-fdb3-5e2c-8725-a6f8f026cc76"
    mock_payload = {
        "statusCode": 200,
        "responseObject": {
            "users": [
                {
                    "id": "cb17d8ae-8b2b-417b-8717-38d58c67c514",
                    "userHandle": "sol_whale",
                    "displayName": "Sol Whale",
                    "address": "B1J2p1wHq9z8XoXmQ1yLh2v8H1i4v1P6d8k9q1a2b3c4",
                    "evmAddress": "0x5ed6946ed712e52b822bbbb3bf3876e5d8ff64e2",
                    "badge": "top_100_badge",
                    "profilePictureLink": None,
                    "followers": 120,
                    "following": 45,
                    "numTrades": 350,
                    "totalVolume": 1500000.5,
                    "pnl24h": 12500.25,
                }
            ],
            "total": 1,
            "page": 1,
            "limit": 50,
        },
    }

    route = respx.get(
        f"https://prod-api.fomo.family/v2/users/{user_id}/followingPaginate"
    ).mock(return_value=httpx.Response(200, json=mock_payload))

    users = await fomo_client.get_user_following_paginate(user_id, page=1, limit=50)

    assert route.called
    request = route.calls.last.request
    assert request.url.params["page"] == "1"
    assert request.url.params["limit"] == "50"
    assert "Bearer header." in request.headers["authorization"]

    assert len(users) == 1
    u = users[0]
    assert isinstance(u, FollowedUser)
    assert u.id == "cb17d8ae-8b2b-417b-8717-38d58c67c514"
    assert u.user_handle == "sol_whale"
    assert u.display_name == "Sol Whale"
    assert u.address == "B1J2p1wHq9z8XoXmQ1yLh2v8H1i4v1P6d8k9q1a2b3c4"
    assert u.evm_address == "0x5ed6946ed712e52b822bbbb3bf3876e5d8ff64e2"
    assert u.badge == "top_100_badge"
    assert u.followers == 120
    assert u.following == 45
    assert u.num_trades == 350
    assert u.total_volume == 1500000.5
    assert u.pnl24h == 12500.25


@pytest.mark.asyncio
@respx.mock
async def test_get_user_following_paginate_empty_or_error(fomo_client):
    user_id = "85fb7b04-fdb3-5e2c-8725-a6f8f026cc76"
    respx.get(
        f"https://prod-api.fomo.family/v2/users/{user_id}/followingPaginate"
    ).mock(return_value=httpx.Response(500, json={"error": "server error"}))

    users = await fomo_client.get_user_following_paginate(user_id)
    assert users == []


@pytest.mark.asyncio
@respx.mock
async def test_get_user_following_paginate_unauthorized(fomo_client):
    user_id = "85fb7b04-fdb3-5e2c-8725-a6f8f026cc76"
    respx.get(
        f"https://prod-api.fomo.family/v2/users/{user_id}/followingPaginate"
    ).mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))

    with pytest.raises(FomoTokenExpiredError):
        await fomo_client.get_user_following_paginate(user_id)


@pytest.mark.asyncio
@respx.mock
async def test_get_leaderboard_success(fomo_client):
    mock_payload = {
        "responseObject": {
            "leaderboard": [
                {
                    "id": "trader1",
                    "userHandle": "whale_master",
                    "displayName": "Whale Master",
                    "address": "SoLAddr11111111111111111111111111111111111",
                    "evmAddress": "0x123",
                    "totalPnL": 50000.0,
                    "numTrades": 200,
                    "totalVolume": 1000000.0,
                    "followers": 50,
                    "topHoldings": [
                        {
                            "tokenAddress": "Token123",
                            "networkId": 1399811149,
                            "value": 15000.0,
                            "pnl": 5000.0,
                            "imageUrl": "https://img.png",
                        }
                    ],
                }
            ]
        }
    }
    respx.get("https://prod-api.fomo.family/v2/leaderboard?limit=20").mock(
        return_value=httpx.Response(200, json=mock_payload)
    )

    traders = await fomo_client.get_leaderboard(limit=20)
    assert len(traders) == 1
    t = traders[0]
    assert isinstance(t, Trader)
    assert t.user_handle == "whale_master"
    assert t.total_pnl == 50000.0
    assert len(t.top_holdings) == 1
    assert t.top_holdings[0].token_address == "Token123"


@pytest.mark.asyncio
@respx.mock
async def test_get_following_success(fomo_client):
    mock_payload = {
        "responseObject": {
            "users": [
                {
                    "id": "u1",
                    "userHandle": "alpha_trader",
                    "displayName": "Alpha",
                    "totalPnL": 25000.0,
                    "numTrades": 40,
                    "totalVolume": 300000.0,
                    "followers": 80,
                }
            ]
        }
    }
    respx.get("https://prod-api.fomo.family/v2/leaderboard/following").mock(
        return_value=httpx.Response(200, json=mock_payload)
    )

    followed = await fomo_client.get_following()
    assert len(followed) == 1
    f = followed[0]
    assert isinstance(f, FollowedTrader)
    assert f.user_handle == "alpha_trader"


@pytest.mark.asyncio
@respx.mock
async def test_get_user_activity_success(fomo_client):
    mock_payload = {
        "responseObject": {
            "activities": [
                {
                    "id": "act1",
                    "type": "DEPOSIT",
                    "tokenAddress": "TokenXYZ",
                    "networkId": 1399811149,
                    "usdAmount": 1200.50,
                    "createdAt": "2026-09-29T10:00:00Z",
                    "tokenMetadata": {"symbol": "MEME"},
                }
            ]
        }
    }
    respx.get("https://prod-api.fomo.family/v2/users/u1/activity?limit=10").mock(
        return_value=httpx.Response(200, json=mock_payload)
    )

    activities = await fomo_client.get_user_activity("u1", limit=10)
    assert len(activities) == 1
    a = activities[0]
    assert isinstance(a, TradeActivity)
    assert a.token_symbol == "MEME"
    assert a.usd_amount == 1200.50
