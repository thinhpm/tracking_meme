import base64
import json
import logging
from pathlib import Path
import time
from typing import Any, NamedTuple

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://prod-api.fomo.family"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class TraderHolding(NamedTuple):
    token_address: str
    network_id: int
    value_usd: float
    pnl_usd: float
    image_url: str


class Trader(NamedTuple):
    id: str
    user_handle: str
    display_name: str
    address: str
    evm_address: str
    total_pnl: float
    num_trades: int
    total_volume: float
    followers: int
    top_holdings: list[TraderHolding]
    rank: int  # 1-indexed position in leaderboard response


_NETWORK_NAMES: dict[int, str] = {
    1: "ETH",
    56: "BSC",
    8453: "Base",
    42161: "ARB",
    1399811149: "SOL",
    4663: "Monad",
}


class TradeActivity(NamedTuple):
    id: str
    token_symbol: str
    token_address: str
    network_id: int
    usd_amount: float
    trade_type: str  # DEPOSIT=buy, WITHDRAWAL=sell
    created_at: str  # ISO timestamp


class FollowedTrader(NamedTuple):
    id: str
    user_handle: str
    display_name: str
    total_pnl: float
    num_trades: int
    total_volume: float
    followers: int


class FomoTokenExpiredError(Exception):
    pass


class FomoTokenProvider:
    """Manages Fomo auth tokens with MongoDB cache, local file, and env fallback."""

    def __init__(
        self,
        db: Any | None = None,
        session_file: str | None = None,
        fallback_token: str | None = None,
    ) -> None:
        self._db = db
        self._session_file = session_file
        self._fallback_token = fallback_token
        self._cached_token: str | None = None

    @staticmethod
    def is_jwt_expired(token: str, skew_seconds: int = 60) -> bool:
        if not token or not isinstance(token, str):
            return True
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return True
            payload = parts[1]
            padded = payload + "=" * (-len(payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")))
            exp = data.get("exp", 0)
            return time.time() + skew_seconds >= exp
        except Exception:
            return True

    async def get_token(self) -> str:
        # 1. Check MongoDB
        if self._db is not None:
            try:
                doc = await self._db["fomo_sessions"].find_one({"_id": "current"})
                if doc:
                    token = doc.get("access_token")
                    if token and not self.is_jwt_expired(token):
                        self._cached_token = token
                        return token
            except Exception as e:
                logger.warning("fomo.token_provider.db_error", extra={"error": str(e)})

        # 2. Check session_file
        if self._session_file:
            path = Path(self._session_file)
            if path.exists() and path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    token = data.get("access_token") or data.get("token")
                    if token and not self.is_jwt_expired(token):
                        self._cached_token = token
                        return token
                except Exception as e:
                    logger.warning("fomo.token_provider.file_error", extra={"error": str(e)})

        # 3. Check fallback_token
        if self._fallback_token and not self.is_jwt_expired(self._fallback_token):
            self._cached_token = self._fallback_token
            return self._fallback_token

        raise FomoTokenExpiredError(
            "No valid Fomo session token found (MongoDB, file, and env fallback all expired or missing)"
        )


class FomoClient:
    def __init__(self, token_or_provider: str | FomoTokenProvider) -> None:
        if isinstance(token_or_provider, FomoTokenProvider):
            self._provider = token_or_provider
        else:
            self._provider = FomoTokenProvider(fallback_token=token_or_provider)

    @property
    def provider(self) -> FomoTokenProvider:
        return self._provider

    async def _headers(self) -> dict[str, str]:
        token = await self._provider.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Supported-Chains": "ethereum,bsc,solana,base,arbitrum",
            "App-Language": "en",
            "User-Agent": _USER_AGENT,
            "Origin": "https://fomo.family",
            "Referer": "https://fomo.family/",
        }

    def is_token_expired(self) -> bool:
        if self._provider._cached_token and not self._provider.is_jwt_expired(self._provider._cached_token):
            return False
        if self._provider._fallback_token and not self._provider.is_jwt_expired(self._provider._fallback_token):
            return False
        return True

    async def get_leaderboard(self, limit: int = 20) -> list[Trader]:
        headers = await self._headers()
        url = f"{_BASE_URL}/v2/leaderboard?limit={limit}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            logger.error("fomo.leaderboard.request_error", extra={"error": str(exc)})
            return []

        if r.status_code == 401:
            raise FomoTokenExpiredError("API returned 401 unauthorized")

        if r.status_code != 200:
            logger.warning("fomo.leaderboard.bad_status", extra={"status": r.status_code})
            return []

        try:
            raw = r.json().get("responseObject", {}).get("leaderboard", [])
        except Exception:
            logger.error("fomo.leaderboard.parse_error")
            return []

        traders: list[Trader] = []
        for rank, item in enumerate(raw[:limit], 1):
            holdings = [
                TraderHolding(
                    token_address=h.get("tokenAddress", ""),
                    network_id=h.get("networkId", 0),
                    value_usd=float(h.get("value") or 0),
                    pnl_usd=float(h.get("pnl") or 0),
                    image_url=h.get("imageUrl", ""),
                )
                for h in item.get("topHoldings", [])[:3]
            ]
            traders.append(
                Trader(
                    id=item.get("id", ""),
                    user_handle=item.get("userHandle", ""),
                    display_name=item.get("displayName", ""),
                    address=item.get("address", ""),
                    evm_address=item.get("evmAddress", ""),
                    total_pnl=float(item.get("totalPnL") or 0),
                    num_trades=int(item.get("numTrades") or 0),
                    total_volume=float(item.get("totalVolume") or 0),
                    followers=int(item.get("followers") or 0),
                    top_holdings=holdings,
                    rank=rank,
                )
            )
        return traders

    async def get_following(self) -> list[FollowedTrader]:
        headers = await self._headers()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{_BASE_URL}/v2/leaderboard/following", headers=headers)
        except httpx.RequestError as exc:
            logger.error("fomo.following.request_error", extra={"error": str(exc)})
            return []
        if r.status_code == 401:
            raise FomoTokenExpiredError("API returned 401 unauthorized")
        if r.status_code != 200:
            return []
        try:
            users = r.json().get("responseObject", {}).get("users", [])
        except Exception:
            return []
        result: list[FollowedTrader] = []
        for u in users:
            result.append(
                FollowedTrader(
                    id=u.get("id", ""),
                    user_handle=u.get("userHandle", ""),
                    display_name=u.get("displayName", ""),
                    total_pnl=float(u.get("totalPnL") or 0),
                    num_trades=int(u.get("numTrades") or 0),
                    total_volume=float(u.get("totalVolume") or 0),
                    followers=int(u.get("followers") or 0),
                )
            )
        return result

    async def get_user_activity(self, user_id: str, limit: int = 10) -> list[TradeActivity]:
        headers = await self._headers()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{_BASE_URL}/v2/users/{user_id}/activity",
                    headers=headers,
                    params={"limit": limit},
                )
        except httpx.RequestError as exc:
            logger.error("fomo.activity.request_error", extra={"error": str(exc), "user_id": user_id})
            return []
        if r.status_code == 401:
            raise FomoTokenExpiredError("API returned 401 unauthorized")
        if r.status_code != 200:
            return []
        try:
            activities = r.json().get("responseObject", {}).get("activities", [])
        except Exception:
            return []
        result: list[TradeActivity] = []
        for a in activities:
            meta = a.get("tokenMetadata") or {}
            result.append(
                TradeActivity(
                    id=a.get("id", ""),
                    token_symbol=meta.get("symbol", ""),
                    token_address=a.get("tokenAddress", ""),
                    network_id=int(a.get("networkId") or 0),
                    usd_amount=float(a.get("usdAmount") or 0),
                    trade_type=a.get("type", ""),
                    created_at=a.get("createdAt", ""),
                )
            )
        return result
