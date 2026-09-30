from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.analysis_service import AnalysisService, heuristic_analysis

MARKET = {
    "price_usd": 0.000285,
    "market_cap": 285000,
    "fdv": 285000,
    "liquidity_usd": 41000,
    "volume": {"m5": 0, "h1": 74000, "h6": 1820000, "h24": 2190000},
    "price_change": {"m5": 3.67, "h1": -8.47, "h6": 274.0, "h24": 23572.0},
    "txns_h24": {"buys": 4220, "sells": 3779},
}

SECURITY = {
    "is_honeypot": False,
    "buy_tax": 0.0,
    "sell_tax": 0.0,
    "lp_locked": False,
}

SOCIAL = {"twitter": "https://twitter.com/henry", "website": None, "telegram": None}


def test_heuristic_volume_8x_mcap_flags_high_risk() -> None:
    result = heuristic_analysis(MARKET, SECURITY, SOCIAL)
    flags_text = " ".join(result["risk_flags"])
    assert "volume" in flags_text.lower() or "pump" in flags_text.lower()
    assert result["risk_level"] in ("HIGH", "VERY_HIGH")


def test_heuristic_honeypot_sets_very_high() -> None:
    sec = {**SECURITY, "is_honeypot": True}
    result = heuristic_analysis(MARKET, sec, SOCIAL)
    assert result["risk_level"] == "VERY_HIGH"


def test_heuristic_low_liquidity_flagged() -> None:
    market = {**MARKET, "liquidity_usd": 10000}
    result = heuristic_analysis(market, SECURITY, SOCIAL)
    flags_text = " ".join(result["risk_flags"])
    assert "liquidity" in flags_text.lower()


def test_heuristic_no_website_flagged() -> None:
    result = heuristic_analysis(MARKET, SECURITY, SOCIAL)
    flags_text = " ".join(result["risk_flags"])
    assert "website" in flags_text.lower()


def test_heuristic_balanced_buysell_positive_flag() -> None:
    result = heuristic_analysis(MARKET, SECURITY, SOCIAL)
    pos_text = " ".join(result["positive_flags"])
    assert "buy" in pos_text.lower() or "cân bằng" in pos_text.lower()


async def test_generate_falls_back_to_heuristic_on_api_error() -> None:
    svc = AnalysisService(api_key="fake-key")
    with patch.object(svc, "_call_claude", side_effect=Exception("api down")):
        result = await svc.generate(MARKET, SECURITY, SOCIAL)
    assert result["risk_level"] in ("LOW", "MEDIUM", "HIGH", "VERY_HIGH")
    assert isinstance(result["risk_flags"], list)


async def test_generate_uses_claude_when_api_key_provided() -> None:
    svc = AnalysisService(api_key="fake-key")
    mock_result = {
        "risk_flags": ["flag 1"],
        "positive_flags": [],
        "summary": "Claude summary",
        "risk_level": "MEDIUM",
    }
    with patch.object(svc, "_call_claude", new=AsyncMock(return_value=mock_result)) as mock_claude:
        res = await svc.generate(MARKET, SECURITY, SOCIAL)
        assert res == mock_result
        mock_claude.assert_awaited_once()


async def test_generate_uses_gemini_when_api_key_empty() -> None:
    mock_gemini = AsyncMock()
    mock_result = {
        "risk_flags": ["gemini risk"],
        "positive_flags": ["gemini positive"],
        "summary": "Gemini summary",
        "risk_level": "LOW",
    }
    mock_gemini.run_json.return_value = mock_result
    svc = AnalysisService(api_key="", gemini_client=mock_gemini)

    res = await svc.generate(MARKET, SECURITY, SOCIAL)
    assert res == mock_result
    mock_gemini.run_json.assert_awaited_once()


async def test_generate_gemini_failure_falls_back_to_heuristic() -> None:
    mock_gemini = AsyncMock()
    mock_gemini.run_json.side_effect = RuntimeError("Gateway timeout")
    svc = AnalysisService(api_key="", gemini_client=mock_gemini)

    res = await svc.generate(MARKET, SECURITY, SOCIAL)
    assert res["risk_level"] in ("LOW", "MEDIUM", "HIGH", "VERY_HIGH")
    assert isinstance(res["risk_flags"], list)


async def test_generate_no_provider_configured_falls_back_to_heuristic() -> None:
    svc = AnalysisService(api_key="", gemini_client=None)
    res = await svc.generate(MARKET, SECURITY, SOCIAL)
    assert res["risk_level"] in ("LOW", "MEDIUM", "HIGH", "VERY_HIGH")

