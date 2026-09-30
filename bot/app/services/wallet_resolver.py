"""Discovers real on-chain execution wallet for a Fomo trader by correlating swap timestamps with block logs."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class FomoSwap(NamedTuple):
    token_address: str
    timestamp: int
    amount_usd: float
    trade_type: str = "BUY"


class ResolutionResult(NamedTuple):
    resolved_wallet: str | None
    confidence: float
    candidate_matches: dict[str, int]


class WalletResolver:
    """Discovers real on-chain execution wallet for a Fomo trader."""

    def __init__(
        self,
        rpc_client: Any = None,
        db: Any = None,
        window_seconds: int = 90,
        min_confidence: float = 0.95,
        fetch_timeout: float = 10.0,
    ) -> None:
        self._rpc_client = rpc_client
        self._db = db
        self._window_seconds = window_seconds
        self._min_confidence = min_confidence
        self._fetch_timeout = fetch_timeout

    async def _fetch_candidate_signers(
        self, chain: str, token_address: str, start_ts: int, end_ts: int
    ) -> list[str]:
        if not self._rpc_client:
            return []
        try:
            if hasattr(self._rpc_client, "get_candidate_signers"):
                return await asyncio.wait_for(
                    self._rpc_client.get_candidate_signers(
                        token_address=token_address,
                        start_ts=start_ts,
                        end_ts=end_ts,
                    ),
                    timeout=self._fetch_timeout,
                )
        except Exception as e:
            logger.warning(
                "wallet_resolver.fetch_signers_failed",
                extra={"token": token_address, "error": str(e)},
            )
        return []

    async def resolve_trader_wallet(
        self,
        trader_handle: str,
        fomo_swaps: list[FomoSwap],
        chain: str = "solana",
    ) -> ResolutionResult:
        """Correlates Fomo swaps with block signers to identify the execution wallet."""
        if not fomo_swaps:
            return ResolutionResult(resolved_wallet=None, confidence=0.0, candidate_matches={})

        # Fetch candidate signers for all swaps concurrently
        tasks = [
            self._fetch_candidate_signers(
                chain=chain,
                token_address=swap.token_address,
                start_ts=swap.timestamp - self._window_seconds,
                end_ts=swap.timestamp + self._window_seconds,
            )
            for swap in fomo_swaps
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates_per_swap: list[set[str]] = []
        for r in results:
            if isinstance(r, list):
                candidates_per_swap.append(set(r))
            else:
                candidates_per_swap.append(set())

        # Count occurrences of each wallet across swaps
        total_swaps = len(fomo_swaps)
        counts: dict[str, int] = {}
        for cand_set in candidates_per_swap:
            for wallet in cand_set:
                counts[wallet] = counts.get(wallet, 0) + 1

        if not counts:
            return ResolutionResult(resolved_wallet=None, confidence=0.0, candidate_matches={})

        best_wallet, best_count = max(counts.items(), key=lambda item: item[1])
        confidence = best_count / total_swaps

        resolved = None
        if confidence >= self._min_confidence:
            resolved = best_wallet
            if self._db is not None:
                try:
                    await self._db["tracked_wallets"].update_one(
                        {"address": resolved, "chain": chain},
                        {
                            "$set": {
                                "address": resolved,
                                "chain": chain,
                                "fomo_handle": trader_handle,
                                "source": "fomo_resolved",
                                "confidence": confidence,
                                "is_active": True,
                                "updated_at": time.time(),
                            },
                            "$setOnInsert": {
                                "created_at": time.time(),
                                "tier": "tier_1",
                                "score": 80.0,
                            },
                        },
                        upsert=True,
                    )
                except Exception as e:
                    logger.error(
                        "wallet_resolver.db_save_failed",
                        extra={"wallet": resolved, "error": str(e)},
                    )

        return ResolutionResult(
            resolved_wallet=resolved,
            confidence=confidence,
            candidate_matches=counts,
        )
