"""Composite scoring engine evaluating Smart Money, Momentum, Safety, Liquidity, and Social heat."""
from __future__ import annotations

import logging
import time
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class TokenSnapshot(NamedTuple):
    token_mint: str
    token_name: str
    token_symbol: str
    chain: str
    risk_passed: bool
    heat_normalized: float       # 0.0 to 1.0 (Smart money heat factor)
    volume_acceleration: float   # 0.0 to 1.0
    security_rating: float       # 0.0 to 1.0
    liquidity_depth: float       # 0.0 to 1.0
    fomo_social_heat: float      # 0.0 to 1.0
    wallets: list[str]
    conviction: float
    age_seconds: float


class ScoredSignal(NamedTuple):
    token_mint: str
    score: int
    tier: str  # "A_GRADE_SNIPER" | "WATCHLIST" | "IGNORE"
    components: dict[str, float]
    snapshot: TokenSnapshot
    timestamp: float


class SignalScorer:
    """Computes weighted composite signal score and determines alert tier."""

    def __init__(self, db: Any = None) -> None:
        self._db = db

    def compute_score(self, snapshot: TokenSnapshot) -> ScoredSignal:
        now = time.time()
        # 1. Hard risk gate check
        if not snapshot.risk_passed:
            return ScoredSignal(
                token_mint=snapshot.token_mint,
                score=0,
                tier="IGNORE",
                components={
                    "smart_money": 0.0,
                    "momentum": 0.0,
                    "safety": 0.0,
                    "liquidity": 0.0,
                    "social": 0.0,
                },
                snapshot=snapshot,
                timestamp=now,
            )

        # 2. Weighted components (0 - 100)
        smart_money = snapshot.heat_normalized * 100.0      # 30%
        momentum = snapshot.volume_acceleration * 100.0    # 25%
        safety = snapshot.security_rating * 100.0          # 20%
        liquidity = snapshot.liquidity_depth * 100.0       # 15%
        social = snapshot.fomo_social_heat * 100.0         # 10%

        raw_score = (
            0.30 * smart_money +
            0.25 * momentum +
            0.20 * safety +
            0.15 * liquidity +
            0.10 * social
        )
        final_score = max(0, min(100, int(raw_score)))

        if final_score >= 80:
            tier = "A_GRADE_SNIPER"
        elif final_score >= 60:
            tier = "WATCHLIST"
        else:
            tier = "IGNORE"

        components = {
            "smart_money": smart_money,
            "momentum": momentum,
            "safety": safety,
            "liquidity": liquidity,
            "social": social,
        }

        return ScoredSignal(
            token_mint=snapshot.token_mint,
            score=final_score,
            tier=tier,
            components=components,
            snapshot=snapshot,
            timestamp=now,
        )

    async def score_and_save(self, snapshot: TokenSnapshot) -> ScoredSignal:
        scored = self.compute_score(snapshot)

        if self._db is not None:
            try:
                await self._db["token_signals"].update_one(
                    {"token_mint": snapshot.token_mint},
                    {
                        "$set": {
                            "token_mint": snapshot.token_mint,
                            "token_name": snapshot.token_name,
                            "token_symbol": snapshot.token_symbol,
                            "chain": snapshot.chain,
                            "score": scored.score,
                            "tier": scored.tier,
                            "components": scored.components,
                            "wallets": snapshot.wallets,
                            "conviction": snapshot.conviction,
                            "age_seconds": snapshot.age_seconds,
                            "status": "qualified" if scored.score >= 80 else "research",
                            "updated_at": scored.timestamp,
                        },
                        "$setOnInsert": {
                            "created_at": scored.timestamp,
                        },
                    },
                    upsert=True,
                )
            except Exception as e:
                logger.error(
                    "signal_scorer.db_save_failed",
                    extra={"token": snapshot.token_mint, "error": str(e)},
                )

        return scored
