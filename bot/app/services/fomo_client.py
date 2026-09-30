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


class FollowedUser(NamedTuple):
    id: str
    address: str  # Solana address
    evm_address: str  # EVM address
    user_handle: str
    display_name: str
    followers: int
    following: int
    num_trades: int
    total_volume: float
    pnl24h: float
    badge: str | None
    profile_picture_link: str | None


class FomoTokenExpiredError(Exception):
    pass


_PRIVY_SESSIONS_URL = "https://auth.privy.io/api/v1/sessions"
_PRIVY_APP_ID = "cm6h485o300n3zj9yl6vpedq7"
_PRIVY_CA_ID = "2b6debb9-793e-4c4b-8f56-ae7a7eba47b2"
_PRIVY_CLIENT = "react-auth:3.34.0"
_PRIVY_CLIENT_ID = "client-WY5gFSayQjxnQhG4rP6SnwPAyPZWZpNRhJ6b9rzMnYwqH"


def _update_env_file(updates: dict[str, str], env_paths: tuple[str, ...] = (".env", "../.env")) -> None:
    import os
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    for env_str in env_paths:
        path = Path(env_str)
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
                lines = content.splitlines()
                new_lines = []
                updated_keys = set()
                for line in lines:
                    stripped = line.strip()
                    matched = False
                    for k, v in updates.items():
                        if stripped.startswith(f"{k}="):
                            new_lines.append(f"{k}={v}")
                            updated_keys.add(k)
                            matched = True
                            break
                    if not matched:
                        new_lines.append(line)
                for k, v in updates.items():
                    if k not in updated_keys:
                        new_lines.append(f"{k}={v}")
                path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                break
            except Exception as e:
                logger.warning("fomo.token_provider.update_env_error", extra={"error": str(e)})


class FomoTokenProvider:
    """Manages Fomo auth tokens with Privy REST auto-refresh, MongoDB cache, local file, and env fallback."""

    def __init__(
        self,
        db: Any | None = None,
        session_file: str | None = None,
        fallback_token: str | None = None,
        refresh_token: str | None = None,
        privy_access_token: str | None = None,
    ) -> None:
        self._db = db
        self._session_file = session_file
        self._fallback_token = fallback_token
        self._refresh_token = refresh_token
        self._privy_access_token = privy_access_token
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

    async def _persist_session(
        self,
        token: str,
        privy_access_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        # 1. Persist to MongoDB
        if self._db is not None:
            try:
                doc: dict[str, Any] = {
                    "access_token": token,
                    "status": "valid",
                    "updated_at": int(time.time()),
                }
                if privy_access_token:
                    doc["privy_access_token"] = privy_access_token
                if refresh_token:
                    doc["refresh_token"] = refresh_token

                await self._db["fomo_sessions"].update_one(
                    {"_id": "current"},
                    {"$set": doc},
                    upsert=True,
                )
            except Exception as e:
                logger.warning("fomo.token_provider.persist_db_error", extra={"error": str(e)})

        # 2. Persist to session file
        if self._session_file:
            try:
                p = Path(self._session_file)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(
                    json.dumps(
                        {
                            "access_token": token,
                            "privy_access_token": privy_access_token or self._privy_access_token,
                            "refresh_token": refresh_token or self._refresh_token,
                            "updated_at": int(time.time()),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.warning("fomo.token_provider.persist_file_error", extra={"error": str(e)})

        # 3. Update local .env file
        env_updates = {"FOMO_PRIVY_TOKEN": token}
        if privy_access_token:
            env_updates["FOMO_PRIVY_ACCESS_TOKEN"] = privy_access_token
        if refresh_token:
            env_updates["FOMO_REFRESH_TOKEN"] = refresh_token
        _update_env_file(env_updates)

    async def refresh_session(self) -> str | None:
        """Refreshes Privy session using the official Privy REST API endpoint."""
        if not self._refresh_token:
            logger.warning("fomo.token_provider.refresh_skipped: no refresh_token configured")
            return None

        bearer = self._privy_access_token or self._cached_token or self._fallback_token
        if not bearer:
            logger.warning("fomo.token_provider.refresh_skipped: no bearer access token for privy auth")
            return None

        headers = {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "authorization": f"Bearer {bearer}",
            "content-type": "application/json",
            "origin": "https://fomo.family",
            "referer": "https://fomo.family/",
            "privy-app-id": _PRIVY_APP_ID,
            "privy-ca-id": _PRIVY_CA_ID,
            "privy-client": _PRIVY_CLIENT,
            "privy-client-id": _PRIVY_CLIENT_ID,
            "user-agent": _USER_AGENT,
        }
        body = {"refresh_token": self._refresh_token}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(_PRIVY_SESSIONS_URL, headers=headers, json=body)
        except Exception as e:
            logger.error("fomo.token_provider.refresh_error", extra={"error": str(e)})
            return None

        if res.status_code != 200:
            logger.warning(
                "fomo.token_provider.refresh_failed",
                extra={"status": res.status_code, "body": res.text[:200]},
            )
            return None

        try:
            data = res.json()
        except Exception:
            logger.error("fomo.token_provider.refresh_json_parse_error")
            return None

        new_token = data.get("token")
        new_pat = data.get("privy_access_token")
        new_rt = data.get("refresh_token")

        if new_pat:
            self._privy_access_token = new_pat
        if new_rt:
            self._refresh_token = new_rt

        effective_token = new_token or self._cached_token or self._fallback_token
        if new_token or (new_pat and effective_token):
            self._cached_token = effective_token
            if effective_token:
                await self._persist_session(
                    token=effective_token,
                    privy_access_token=self._privy_access_token,
                    refresh_token=self._refresh_token,
                )
            logger.info("fomo.token_provider.refresh_success: session refreshed")
            return effective_token
        elif self._cached_token and not self.is_jwt_expired(self._cached_token):
            return self._cached_token

        return None

    async def get_token(self) -> str:
        # 0. In-memory cached token
        if self._cached_token and not self.is_jwt_expired(self._cached_token):
            return self._cached_token

        # 1. Check MongoDB
        if self._db is not None:
            try:
                doc = await self._db["fomo_sessions"].find_one({"_id": "current"})
                if doc:
                    if doc.get("privy_access_token"):
                        self._privy_access_token = doc.get("privy_access_token")
                    if doc.get("refresh_token"):
                        self._refresh_token = doc.get("refresh_token")
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
                    if data.get("privy_access_token"):
                        self._privy_access_token = data.get("privy_access_token")
                    if data.get("refresh_token"):
                        self._refresh_token = data.get("refresh_token")
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

        # 4. Attempt auto-refresh via Privy REST API
        if self._refresh_token:
            try:
                new_token = await self.refresh_session()
                if new_token:
                    return new_token
            except Exception as e:
                logger.warning("fomo.token_provider.auto_refresh_error", extra={"error": str(e)})

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

    async def get_user_following_paginate(
        self, user_id: str, page: int = 1, limit: int = 50
    ) -> list[FollowedUser]:
        headers = await self._headers()
        url = f"{_BASE_URL}/v2/users/{user_id}/followingPaginate"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    url,
                    headers=headers,
                    params={"page": page, "limit": limit},
                )
        except httpx.RequestError as exc:
            logger.error(
                "fomo.following_paginate.request_error",
                extra={"error": str(exc), "user_id": user_id},
            )
            return []

        if r.status_code == 401:
            raise FomoTokenExpiredError("API returned 401 unauthorized")
        if r.status_code != 200:
            logger.warning(
                "fomo.following_paginate.bad_status",
                extra={"status": r.status_code, "user_id": user_id},
            )
            return []

        try:
            raw_users = r.json().get("responseObject", {}).get("users", [])
        except Exception:
            logger.error("fomo.following_paginate.parse_error", extra={"user_id": user_id})
            return []

        result: list[FollowedUser] = []
        for u in raw_users:
            result.append(
                FollowedUser(
                    id=u.get("id", ""),
                    address=u.get("address") or "",
                    evm_address=u.get("evmAddress") or "",
                    user_handle=u.get("userHandle") or "",
                    display_name=u.get("displayName") or "",
                    followers=int(u.get("followers") or 0),
                    following=int(u.get("following") or 0),
                    num_trades=int(u.get("numTrades") or 0),
                    total_volume=float(u.get("totalVolume") or 0.0),
                    pnl24h=float(u.get("pnl24h") or 0.0),
                    badge=u.get("badge"),
                    profile_picture_link=u.get("profilePictureLink"),
                )
            )
        return result
