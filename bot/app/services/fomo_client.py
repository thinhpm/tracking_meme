"""HTTP client for prod-api.fomo.family."""
from __future__ import annotations

import logging
import time
from typing import NamedTuple

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


class FomoTokenExpiredError(Exception):
    pass


class FomoClient:
    def __init__(self, token: str) -> None:
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "X-Supported-Chains": "ethereum,bsc,solana,base,arbitrum",
            "App-Language": "en",
            "User-Agent": _USER_AGENT,
            "Origin": "https://fomo.family",
            "Referer": "https://fomo.family/",
        }

    def is_token_expired(self) -> bool:
        try:
            import base64, json as _json
            parts = self._token.split(".")
            if len(parts) != 3:
                return True
            payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
            data = _json.loads(base64.b64decode(payload))
            return time.time() > data.get("exp", 0)
        except Exception:
            return True

    async def get_leaderboard(self, limit: int = 20) -> list[Trader]:
        if self.is_token_expired():
            raise FomoTokenExpiredError("Privy token expired")

        url = f"{_BASE_URL}/v2/leaderboard?limit={limit}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, headers=self._headers())
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
