"""Realtime smart money consensus and earlyness decay engine."""
from __future__ import annotations

from collections import defaultdict
import logging
import time
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


def compute_earlyness_factor(age_seconds: float) -> float:
    """Computes the earlyness decay multiplier based on token age at buy time."""
    if age_seconds <= 60.0:
        return 1.0
    elif age_seconds <= 1800.0:  # <= 30m
        return 0.5
    elif age_seconds <= 36000.0:  # <= 10h
        return 0.25
    else:
        return 0.1


class WalletBuyEvent(NamedTuple):
    token_mint: str
    wallet_address: str
    wallet_score: float  # 0 to 100
    timestamp: float
    amount_usd: float
    launch_timestamp: float | None = None


class ConsensusSignal(NamedTuple):
    token_mint: str
    wallets: list[str]
    conviction: float
    earlyness: float
    heat: float
    is_consensus: bool
    timestamp: float


class ConsensusEngine:
    """Aggregates real-time buy events in a sliding window to detect Smart Money Clusters."""

    def __init__(
        self,
        db: Any = None,
        window_seconds: float = 60.0,
        min_conviction: float = 1.3,
    ) -> None:
        self._db = db
        self._window_seconds = window_seconds
        self._min_conviction = min_conviction
        self._windows: dict[str, list[WalletBuyEvent]] = defaultdict(list)

    def cleanup_stale_windows(self, now: float | None = None) -> None:
        """Removes token windows that have had no activity within the window duration."""
        current_time = now or time.time()
        expired_tokens = [
            token
            for token, buys in self._windows.items()
            if not buys or (current_time - buys[-1].timestamp > self._window_seconds * 2)
        ]
        for token in expired_tokens:
            del self._windows[token]

    async def add_buy(self, event: WalletBuyEvent) -> ConsensusSignal:
        """Processes a new buy event and evaluates cluster consensus and heat."""
        token_buys = self._windows[event.token_mint]

        # Prune buys older than sliding window
        fresh_buys = [
            b for b in token_buys if (event.timestamp - b.timestamp) <= self._window_seconds
        ]
        fresh_buys.append(event)
        self._windows[event.token_mint] = fresh_buys

        # Aggregate unique wallets and best scores in this window
        wallet_scores: dict[str, float] = {}
        for b in fresh_buys:
            if b.wallet_address not in wallet_scores or b.wallet_score > wallet_scores[b.wallet_address]:
                wallet_scores[b.wallet_address] = b.wallet_score

        unique_wallets = list(wallet_scores.keys())

        # Conviction = sum((Score(W_i) / 100)^2)
        conviction = sum((score / 100.0) ** 2 for score in wallet_scores.values())
        is_consensus = len(unique_wallets) >= 2 and conviction >= self._min_conviction

        # Earlyness calculation
        if event.launch_timestamp is not None:
            age = max(0.0, event.timestamp - event.launch_timestamp)
            earlyness = compute_earlyness_factor(age)
        else:
            earlyness = 1.0

        heat = conviction * earlyness

        # Persist to database if consensus formed
        if is_consensus and self._db is not None:
            try:
                await self._db["token_signals"].update_one(
                    {"token_mint": event.token_mint},
                    {
                        "$set": {
                            "token_mint": event.token_mint,
                            "wallets": unique_wallets,
                            "conviction": conviction,
                            "earlyness": earlyness,
                            "heat": heat,
                            "is_consensus": True,
                            "status": "consensus_detected",
                            "updated_at": event.timestamp,
                        },
                        "$setOnInsert": {
                            "created_at": event.timestamp,
                        },
                    },
                    upsert=True,
                )
            except Exception as e:
                logger.error(
                    "consensus_engine.db_save_failed",
                    extra={"token": event.token_mint, "error": str(e)},
                )

        return ConsensusSignal(
            token_mint=event.token_mint,
            wallets=unique_wallets,
            conviction=conviction,
            earlyness=earlyness,
            heat=heat,
            is_consensus=is_consensus,
            timestamp=event.timestamp,
        )
