"""Composite scoring engine evaluating Smart Money, Momentum, Safety, Liquidity, and Social heat."""
from __future__ import annotations

import logging
import time
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


def compute_dynamic_momentum(buys_h1: int, sells_h1: int, price_change_h1: float) -> float:
    """Computes dynamic momentum (0.0 to 1.0) combining buy pressure and price acceleration."""
    total_tx = max(buys_h1 + sells_h1, 1)
    buy_ratio = buys_h1 / total_tx
    # price change factor: 0% -> 0.5; +100% -> 1.0; -100% -> 0.0
    price_factor = max(0.0, min(1.0, 0.5 + (price_change_h1 / 200.0)))
    acceleration = 0.6 * buy_ratio + 0.4 * price_factor
    return max(0.0, min(1.0, acceleration))


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

        # Hard liquidity floor: dried pools cannot qualify as sniper-grade
        if snapshot.liquidity_depth < 0.20:
            final_score = min(final_score, 65)

        if final_score >= 80 and snapshot.liquidity_depth >= 0.20:
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
                            "token_address": snapshot.token_mint,
                            "token_name": snapshot.token_name,
                            "token_symbol": snapshot.token_symbol,
                            "chain": snapshot.chain,
                            "score": scored.score,
                            "tier": scored.tier,
                            "components": scored.components,
                            "wallets": snapshot.wallets,
                            "conviction": snapshot.conviction,
                            "age_seconds": snapshot.age_seconds,
                            "status": "qualified" if (scored.score >= 80 and scored.tier == "A_GRADE_SNIPER") else "research",
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
