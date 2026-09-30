import base64
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.fomo_client import (
    FomoClient,
    FomoTokenProvider,
    FomoTokenExpiredError,
)


def make_jwt(exp_timestamp: int) -> str:
    header = base64.b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    payload = base64.b64encode(json.dumps({"exp": exp_timestamp}).encode()).decode().rstrip("=")
    signature = "signature"
    return f"{header}.{payload}.{signature}"


def test_is_jwt_expired():
    now = int(time.time())
    valid_token = make_jwt(now + 3600)
    expired_token = make_jwt(now - 100)
    soon_expired_token = make_jwt(now + 30)  # expires within 60s skew

    assert FomoTokenProvider.is_jwt_expired(valid_token) is False
    assert FomoTokenProvider.is_jwt_expired(expired_token) is True
    assert FomoTokenProvider.is_jwt_expired(soon_expired_token) is True
    assert FomoTokenProvider.is_jwt_expired("invalid.jwt") is True


@pytest.mark.asyncio
async def test_token_provider_from_mongodb():
    now = int(time.time())
    valid_token = make_jwt(now + 3600)

    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value={
        "_id": "current",
        "access_token": valid_token,
        "status": "valid",
    })
    mock_db.__getitem__.return_value = mock_collection

    provider = FomoTokenProvider(db=mock_db)
    token = await provider.get_token()

    assert token == valid_token
    mock_collection.find_one.assert_called_once_with({"_id": "current"})


@pytest.mark.asyncio
async def test_token_provider_fallback_to_file(tmp_path):
    now = int(time.time())
    valid_token = make_jwt(now + 3600)

    session_file = tmp_path / "fomo_session.json"
    session_file.write_text(json.dumps({"access_token": valid_token}))

    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__.return_value = mock_collection

    provider = FomoTokenProvider(db=mock_db, session_file=str(session_file))
    token = await provider.get_token()

    assert token == valid_token


@pytest.mark.asyncio
async def test_token_provider_fallback_to_env():
    now = int(time.time())
    valid_token = make_jwt(now + 3600)

    provider = FomoTokenProvider(
        fallback_token=valid_token,
        session_file="/nonexistent/path/fomo_session.json",
        db=None,
    )
    token = await provider.get_token()
    assert token == valid_token


@pytest.mark.asyncio
async def test_token_provider_all_expired_raises_error():
    now = int(time.time())
    expired_token = make_jwt(now - 100)

    provider = FomoTokenProvider(
        fallback_token=expired_token,
        session_file="/nonexistent/path/fomo_session.json",
        db=None,
    )

    with pytest.raises(FomoTokenExpiredError):
        await provider.get_token()


@pytest.mark.asyncio
async def test_fomo_client_uses_token_provider():
    now = int(time.time())
    valid_token = make_jwt(now + 3600)
    provider = FomoTokenProvider(fallback_token=valid_token, session_file="", db=None)

    client = FomoClient(provider)
    headers = await client._headers()

    assert headers["Authorization"] == f"Bearer {valid_token}"
    assert headers["Origin"] == "https://fomo.family"


@pytest.mark.asyncio
async def test_token_provider_auto_refreshes_when_expired(tmp_path):
    now = int(time.time())
    expired_token = make_jwt(now - 100)
    fresh_token = make_jwt(now + 3600)
    fresh_pat = "new_privy_access_token"

    session_file = tmp_path / "fomo_session.json"
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.update_one = AsyncMock()
    mock_db.__getitem__.return_value = mock_collection

    provider = FomoTokenProvider(
        db=mock_db,
        session_file=str(session_file),
        fallback_token=expired_token,
        refresh_token="mock_refresh_token",
        privy_access_token="old_privy_access_token",
    )

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "token": fresh_token,
            "privy_access_token": fresh_pat,
            "refresh_token": None,
        }
        mock_post.return_value = mock_response

        token = await provider.get_token()
        assert token == fresh_token
        assert provider._privy_access_token == fresh_pat
        assert session_file.exists()
        saved = json.loads(session_file.read_text(encoding="utf-8"))
        assert saved["access_token"] == fresh_token
        mock_collection.update_one.assert_called_once()
