import pytest
from unittest.mock import patch, AsyncMock
import httpx
from app.services.rugcheck_client import RugCheckClient, RugCheckReport, fetch_token_audit


@pytest.mark.asyncio
async def test_rugcheck_client_success_revoked():
    client = RugCheckClient()
    mock_response = httpx.Response(
        200,
        json={
            "token": {"mintAuthority": None, "freezeAuthority": None},
            "markets": [{"lp": {"lpLockedPct": 95.5}}],
            "topHolders": [
                {"address": "H1xxxx", "pct": 4.5},
                {"address": "H2xxxx", "pct": 3.2},
            ],
        },
        request=httpx.Request("GET", "https://api.rugcheck.xyz/v1/tokens/test_mint_123/report"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        report = await client.fetch_token_audit("test_mint_123")

        assert report.risk_passed is True
        assert report.mint_auth == "Revoked"
        assert report.freeze_auth == "Revoked"
        assert report.lp_status == "95% Burned"
        assert report.raw_lp_ratio == 0.955
        assert len(report.top_holders) == 2

        audit_input = report.to_audit_input(buys_24h=20, sells_24h=10)
        assert audit_input.mint_authority is None
        assert audit_input.freeze_authority is None
        assert audit_input.lp_locked_or_burned_ratio == 0.955


@pytest.mark.asyncio
async def test_rugcheck_client_failed_checks():
    client = RugCheckClient()
    mock_response = httpx.Response(
        200,
        json={
            "token": {"mintAuthority": "ActiveDevAddress123", "freezeAuthority": "ActiveFreezeDev123"},
            "markets": [{"lp": {"lpLockedPct": 40.0}}],
            "topHolders": [
                {"address": "Whale1", "pct": 40.0},
            ],
        },
        request=httpx.Request("GET", "https://api.rugcheck.xyz/v1/tokens/bad_mint/report"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        report = await client.fetch_token_audit("bad_mint")

        assert report.risk_passed is False
        assert "Active" in report.mint_auth
        assert "Active" in report.freeze_auth
        assert report.raw_lp_ratio == 0.40


@pytest.mark.asyncio
async def test_rugcheck_client_network_error():
    client = RugCheckClient()
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Network unreachable")):
        report = await client.fetch_token_audit("err_mint")

        assert report.risk_passed is False
        assert report.mint_auth == "Unverified"
        assert report.freeze_auth == "Unverified"
        assert report.lp_status == "Unverified"


@pytest.mark.asyncio
async def test_global_fetch_token_audit():
    with patch("app.services.rugcheck_client._default_rugcheck_client.fetch_token_audit") as mock_fn:
        mock_fn.return_value = RugCheckReport(
            mint_auth="Revoked",
            freeze_auth="Revoked",
            lp_status="100% Burned",
            top_10_share="10%",
            sell_tax="0% Tax",
            risk_passed=True,
            raw_mint_auth=None,
            raw_freeze_auth=None,
            raw_lp_ratio=1.0,
            raw_top_10_ratio=0.10,
            top_holders=[],
        )
        res = await fetch_token_audit("sample_mint")
        assert res.risk_passed is True
        mock_fn.assert_called_once_with("sample_mint")
