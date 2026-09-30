"""Anti-Sybil and provenance verification for smart money buyer clusters."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)

DEFAULT_DUST_FLOOR_USD = 10.0
DEFAULT_DUST_RATIO = 0.05
WAVE_MIN_WALLETS = 3
WAVE_WINDOW_SECONDS = 86400.0  # 24 hours


def is_dust_buy(usd_value: float, median_buy_usd: float | None = None) -> bool:
    """Determines whether a buy fill is dust relative to absolute floor or wallet's median."""
    median = median_buy_usd or 0.0
    threshold = max(DEFAULT_DUST_FLOOR_USD, DEFAULT_DUST_RATIO * median)
    return usd_value < threshold


def classify_fill(
    is_direct: bool = False,
    usd_value: float = 0.0,
    median_buy_usd: float | None = None,
) -> str:
    """Classifies a transaction fill as 'direct' (router injection), 'dust', or 'trade'."""
    if is_direct:
        return "direct"
    if is_dust_buy(usd_value, median_buy_usd):
        return "dust"
    return "trade"


class ProvenanceResult(NamedTuple):
    is_sybil: bool
    max_funder_share: float
    common_funder: str | None
    funder_map: dict[str, str]


class ProvenanceChecker:
    """Detects sybil crews by analyzing common parent funding wallets and seeding waves."""

    def __init__(
        self,
        rpc_client: Any = None,
        db: Any = None,
        max_funder_share_threshold: float = 0.40,
    ) -> None:
        self._rpc_client = rpc_client
        self._db = db
        self._threshold = max_funder_share_threshold
        self._memory_cache: dict[str, str] = {}
        # token_mint -> list of (wallet, timestamp)
        self._suspicious_fills: dict[str, list[tuple[str, float]]] = {}

    def record_and_check_wave(
        self,
        token_mint: str,
        wallet: str,
        kind: str,
        timestamp: float | None = None,
    ) -> tuple[bool, str]:
        """Tracks dust/direct fills for tokens. If >= 3 distinct wallets receive them in 24h, flags SEEDED_WAVE."""
        now = timestamp or time.time()
        if kind not in ("dust", "direct"):
            return False, "CLEAN"

        history = self._suspicious_fills.get(token_mint, [])
        # Prune older than 24 hours
        history = [entry for entry in history if (now - entry[1]) <= WAVE_WINDOW_SECONDS]
        history.append((wallet, now))
        self._suspicious_fills[token_mint] = history

        distinct_wallets = {w for w, _ in history}
        if len(distinct_wallets) >= WAVE_MIN_WALLETS:
            return True, f"SEEDED_WAVE: {len(distinct_wallets)} smart wallets received dust/direct fills in 24h"

        return False, "CLEAN"


    async def get_wallet_funder(self, wallet: str) -> str:
        """Determines the parent funding wallet, checking memory cache, DB, then RPC."""
        # 1. Memory cache check
        if wallet in self._memory_cache:
            return self._memory_cache[wallet]

        # 2. Database cache check
        if self._db is not None:
            try:
                doc = await self._db["wallet_provenance"].find_one({"_id": wallet})
                if doc and "funder" in doc:
                    funder = doc["funder"]
                    self._memory_cache[wallet] = funder
                    return funder
            except Exception as e:
                logger.warning(
                    "provenance.db_lookup_failed",
                    extra={"wallet": wallet, "error": str(e)},
                )

        # 3. RPC resolution
        funder = wallet
        if self._rpc_client and hasattr(self._rpc_client, "get_initial_funder"):
            try:
                res = self._rpc_client.get_initial_funder(wallet)
                if asyncio.iscoroutine(res):
                    res = await res
                if res:
                    funder = res
            except Exception as e:
                logger.warning(
                    "provenance.rpc_lookup_failed",
                    extra={"wallet": wallet, "error": str(e)},
                )

        # Store in caches
        self._memory_cache[wallet] = funder
        if self._db is not None:
            try:
                await self._db["wallet_provenance"].update_one(
                    {"_id": wallet},
                    {
                        "$set": {
                            "_id": wallet,
                            "funder": funder,
                            "updated_at": time.time(),
                        }
                    },
                    upsert=True,
                )
            except Exception as e:
                logger.error(
                    "provenance.db_cache_save_failed",
                    extra={"wallet": wallet, "error": str(e)},
                )

        return funder

    async def check_cluster_provenance(self, wallets: list[str]) -> ProvenanceResult:
        """Evaluates whether >= threshold (e.g. 40%) of wallets share the same parent funder."""
        if not wallets:
            return ProvenanceResult(
                is_sybil=False,
                max_funder_share=0.0,
                common_funder=None,
                funder_map={},
            )

        k = len(wallets)
        tasks = [self.get_wallet_funder(w) for w in wallets]
        funders = await asyncio.gather(*tasks)

        funder_map = {w: f for w, f in zip(wallets, funders)}
        funder_counts: dict[str, int] = {}
        for f in funders:
            funder_counts[f] = funder_counts.get(f, 0) + 1

        top_funder, top_count = max(funder_counts.items(), key=lambda item: item[1])
        funder_share = top_count / k

        is_sybil = top_count >= 2 and funder_share >= self._threshold
        return ProvenanceResult(
            is_sybil=is_sybil,
            max_funder_share=funder_share if top_count >= 2 else 0.0,
            common_funder=top_funder if is_sybil else None,
            funder_map=funder_map,
        )
