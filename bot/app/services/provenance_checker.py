"""Anti-Sybil and provenance verification for smart money buyer clusters."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class ProvenanceResult(NamedTuple):
    is_sybil: bool
    max_funder_share: float
    common_funder: str | None
    funder_map: dict[str, str]


class ProvenanceChecker:
    """Detects sybil crews by analyzing common parent funding wallets."""

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
