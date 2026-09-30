from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.exceptions import AppError
from app.main import app

_REPORT = {
    "token": {"address": "0xabc", "name": "Henry", "symbol": "HENRY", "chain": "eth", "dex": "uniswap"},
    "market": {
        "price_usd": 0.000285, "market_cap": 285000, "fdv": 285000, "liquidity_usd": 41000,
        "volume": {"m5": 0, "h1": 74000, "h6": 1820000, "h24": 2190000},
        "price_change": {"m5": 3.67, "h1": -8.47, "h6": 274.0, "h24": 23572.0},
        "txns_h24": {"buys": 4220, "sells": 3779},
    },
    "security": {
        "is_honeypot": False, "buy_tax": 0.0, "sell_tax": 0.0, "is_open_source": True,
        "owner_address": None, "creator_address": None, "holder_count": 1200,
        "top_10_holders_pct": 45.2, "lp_locked": False,
    },
    "social": {"twitter": "https://twitter.com/henry", "website": None, "telegram": None},
    "analysis": {"risk_flags": ["test"], "positive_flags": [], "summary": "ok", "risk_level": "HIGH"},
    "data_source": "dexscreener",
    "fetched_at": "2026-09-21T10:00:00+00:00",
}


async def test_search_returns_200_with_report() -> None:
    mock_svc = AsyncMock()
    mock_svc.search.return_value = _REPORT

    with patch("app.routes.token._build_service", return_value=mock_svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/token/search",
                json={"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["token"]["symbol"] == "HENRY"


async def test_search_invalid_address_returns_422() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/token/search", json={"address": "notanaddress"})
    assert response.status_code == 422


async def test_search_token_not_found_returns_404() -> None:
    mock_svc = AsyncMock()
    mock_svc.search.side_effect = AppError("Token not found", 404, "TOKEN_NOT_FOUND")

    with patch("app.routes.token._build_service", return_value=mock_svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/token/search",
                json={"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"},
            )

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "TOKEN_NOT_FOUND"


def test_build_service_uses_gemini_when_anthropic_key_empty() -> None:
    from app.config import Settings
    from app.routes.token import _build_service

    dummy_settings = Settings(
        anthropic_api_key="",
        gemini_service_url="http://custom:8000",
        gemini_service_provider="9router",
        gemini_service_model="custom-model",
    )
    with patch("app.routes.token.get_settings", return_value=dummy_settings):
        svc = _build_service()
        assert svc._analysis._gemini is not None
        assert svc._analysis._gemini.base_url == "http://custom:8000"
        assert svc._analysis._gemini.provider == "9router"
        assert svc._analysis._gemini.model == "custom-model"
        assert svc._analysis._client is None


def test_build_service_uses_anthropic_when_key_present() -> None:
    from app.config import Settings
    from app.routes.token import _build_service

    dummy_settings = Settings(
        anthropic_api_key="sk-ant-test-key",
    )
    with patch("app.routes.token.get_settings", return_value=dummy_settings):
        svc = _build_service()
        assert svc._analysis._gemini is None
        assert svc._analysis._client is not None

