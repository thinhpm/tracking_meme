"""HTTP client for api.zerion.io v1."""
from __future__ import annotations

import base64
import logging
from typing import NamedTuple

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.zerion.io"


def _auth_header(api_key: str) -> str:
    encoded = base64.b64encode(f"{api_key}:".encode()).decode()
    return f"Basic {encoded}"


class WalletPortfolio(NamedTuple):
    address: str
    total_usd: float
    change_1d_usd: float
    change_1d_pct: float | None
    by_chain: dict[str, float]  # chain_id → usd value


class TokenPosition(NamedTuple):
    symbol: str
    name: str
    value_usd: float
    quantity: float
    chain_id: str
    contract_address: str  # empty for native tokens
    verified: bool


class TradeTransfer(NamedTuple):
    symbol: str
    contract_address: str
    chain_id: str
    direction: str  # "in" or "out"
    value_usd: float
    quantity: float


class WalletTransaction(NamedTuple):
    tx_hash: str
    operation_type: str  # trade, receive, send, approve, etc.
    mined_at: str  # ISO timestamp
    chain_id: str
    transfers: list[TradeTransfer]


class ZerionClient:
    def __init__(self, api_key: str) -> None:
        self._headers = {
            "Authorization": _auth_header(api_key),
            "Accept": "application/json",
        }

    async def get_portfolio(self, address: str) -> WalletPortfolio | None:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    f"{_BASE_URL}/v1/wallets/{address}/portfolio",
                    headers=self._headers,
                )
        except httpx.RequestError as exc:
            logger.error("zerion.portfolio.request_error", extra={"error": str(exc)})
            return None

        if r.status_code != 200:
            logger.warning("zerion.portfolio.bad_status", extra={"status": r.status_code})
            return None

        try:
            attr = r.json()["data"]["attributes"]
            total = attr.get("total", {}).get("positions", 0.0) or 0.0
            changes = attr.get("changes") or {}
            by_chain: dict[str, float] = {
                k: v for k, v in (attr.get("positions_distribution_by_chain") or {}).items() if v
            }
            return WalletPortfolio(
                address=address,
                total_usd=float(total),
                change_1d_usd=float(changes.get("absolute_1d") or 0),
                change_1d_pct=changes.get("percent_1d"),
                by_chain=by_chain,
            )
        except Exception:
            logger.exception("zerion.portfolio.parse_error")
            return None

    async def get_positions(self, address: str, limit: int = 10) -> list[TokenPosition]:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    f"{_BASE_URL}/v1/wallets/{address}/positions/",
                    headers=self._headers,
                    params={
                        "filter[positions]": "only_simple",
                        "filter[trash]": "only_non_trash",
                        "sort": "-value",
                        "page[size]": limit,
                        "currency": "usd",
                    },
                )
        except httpx.RequestError as exc:
            logger.error("zerion.positions.request_error", extra={"error": str(exc)})
            return []

        if r.status_code != 200:
            return []

        try:
            items = r.json().get("data", [])
        except Exception:
            return []

        result: list[TokenPosition] = []
        for item in items:
            a = item.get("attributes", {})
            fi = a.get("fungible_info", {})
            impls = fi.get("implementations", [])
            impl = impls[0] if impls else {}
            value = a.get("value") or 0
            if not value:
                continue
            result.append(
                TokenPosition(
                    symbol=fi.get("symbol", ""),
                    name=fi.get("name", ""),
                    value_usd=float(value),
                    quantity=float((a.get("quantity") or {}).get("float") or 0),
                    chain_id=impl.get("chain_id", ""),
                    contract_address=impl.get("address", "") or "",
                    verified=fi.get("flags", {}).get("verified", False),
                )
            )
        return result

    async def get_transactions(
        self,
        address: str,
        limit: int = 10,
        operation_types: str | None = None,
    ) -> list[WalletTransaction]:
        params: dict[str, str | int] = {"page[size]": limit, "currency": "usd"}
        if operation_types:
            params["filter[operation_types]"] = operation_types

        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    f"{_BASE_URL}/v1/wallets/{address}/transactions/",
                    headers=self._headers,
                    params=params,
                )
        except httpx.RequestError as exc:
            logger.error("zerion.transactions.request_error", extra={"error": str(exc)})
            return []

        if r.status_code != 200:
            return []

        try:
            items = r.json().get("data", [])
        except Exception:
            return []

        result: list[WalletTransaction] = []
        for item in items:
            a = item.get("attributes", {})
            # infer chain from fee implementation or first transfer
            chain_id = ""
            fee = a.get("fee") or {}
            fee_impls = (fee.get("fungible_info") or {}).get("implementations", [])
            if fee_impls:
                chain_id = fee_impls[0].get("chain_id", "")

            transfers: list[TradeTransfer] = []
            for t in (a.get("transfers") or []):
                fi = t.get("fungible_info") or {}
                impls = fi.get("implementations", [])
                impl = impls[0] if impls else {}
                if not chain_id and impl.get("chain_id"):
                    chain_id = impl["chain_id"]
                transfers.append(
                    TradeTransfer(
                        symbol=fi.get("symbol", ""),
                        contract_address=impl.get("address", "") or "",
                        chain_id=impl.get("chain_id", chain_id),
                        direction=t.get("direction", ""),
                        value_usd=float(t.get("value") or 0),
                        quantity=float((t.get("quantity") or {}).get("float") or 0),
                    )
                )

            result.append(
                WalletTransaction(
                    tx_hash=a.get("hash", ""),
                    operation_type=a.get("operation_type", ""),
                    mined_at=a.get("mined_at", ""),
                    chain_id=chain_id,
                    transfers=transfers,
                )
            )
        return result
