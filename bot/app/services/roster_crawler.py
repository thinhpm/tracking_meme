"""Crawls top traders' following networks to expand the tracked smart money roster."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.services.fomo_client import FomoClient, FollowedUser

logger = logging.getLogger(__name__)


def compute_expanded_wallet_score(
    pnl24h: float,
    total_volume: float,
    num_trades: int,
    peer_endorsement_count: int,
    badge: str | None,
) -> float:
    """Calculates a baseline conviction score (0-100) for a discovered wallet."""
    score = 50.0

    # Peer endorsement bonus: +10 pts each, capped at 25 pts
    score += min(25.0, peer_endorsement_count * 10.0)

    # Badge bonus
    if badge and "top_100" in badge:
        score += 15.0
    elif badge:
        score += 5.0

    # Volume bonus
    if total_volume >= 1_000_000:
        score += 10.0
    elif total_volume >= 100_000:
        score += 5.0

    # 24h PnL bonus/penalty
    if pnl24h >= 10_000:
        score += 10.0
    elif pnl24h > 0:
        score += 5.0
    elif pnl24h < 0:
        score -= 5.0

    return min(100.0, max(0.0, score))


class RosterCrawler:
    """Crawls top traders' following networks to expand the tracked smart money roster."""

    def __init__(
        self,
        fomo_client: FomoClient,
        db: Any = None,
        sleep_delay: float = 0.5,
    ) -> None:
        self._fomo_client = fomo_client
        self._db = db
        self._sleep_delay = sleep_delay

    async def crawl_top_traders_network(
        self,
        top_n: int = 20,
    ) -> dict[str, int]:
        """Fetches top traders from the leaderboard and crawls their followed traders."""
        top_traders = await self._fomo_client.get_leaderboard(limit=top_n)

        followed_users_map: dict[str, FollowedUser] = {}
        endorsers_map: dict[str, set[str]] = {}

        now = time.time()
        for trader in top_traders:
            # Upsert the top trader as Tier 1
            if self._db is not None and trader.address:
                try:
                    await self._db["tracked_wallets"].update_one(
                        {"address": trader.address, "chain": "solana"},
                        {
                            "$set": {
                                "address": trader.address,
                                "chain": "solana",
                                "fomo_id": trader.id,
                                "fomo_handle": trader.user_handle,
                                "display_name": trader.display_name,
                                "source": "fomo_leaderboard",
                                "tier": "tier_1",
                                "score": 95.0,
                                "rank": trader.rank,
                                "total_pnl": trader.total_pnl,
                                "total_volume": trader.total_volume,
                                "is_active": True,
                                "updated_at": now,
                            },
                            "$setOnInsert": {
                                "created_at": now,
                            },
                        },
                        upsert=True,
                    )
                except Exception as e:
                    logger.warning(
                        "roster_crawler.upsert_top_trader_failed",
                        extra={"trader_id": trader.id, "error": str(e)},
                    )

            # Fetch following network
            try:
                following = await self._fomo_client.get_user_following_paginate(
                    trader.id, page=1, limit=50
                )
                for f_user in following:
                    user_key = f_user.address or f_user.id
                    followed_users_map[user_key] = f_user
                    if user_key not in endorsers_map:
                        endorsers_map[user_key] = set()
                    endorsers_map[user_key].add(trader.user_handle)
            except Exception as e:
                logger.warning(
                    "roster_crawler.crawl_user_following_failed",
                    extra={"trader_id": trader.id, "error": str(e)},
                )

            if self._sleep_delay > 0:
                await asyncio.sleep(self._sleep_delay)

        # Upsert all followed users into MongoDB
        solana_count = 0
        evm_count = 0

        for user_key, f_user in followed_users_map.items():
            endorsed_by = sorted(list(endorsers_map.get(user_key, set())))
            endorsement_count = len(endorsed_by)
            tier = "tier_2" if endorsement_count >= 2 else "tier_3"
            score = compute_expanded_wallet_score(
                pnl24h=f_user.pnl24h,
                total_volume=f_user.total_volume,
                num_trades=f_user.num_trades,
                peer_endorsement_count=endorsement_count,
                badge=f_user.badge,
            )

            # Upsert Solana address if present
            if f_user.address and self._db is not None:
                try:
                    await self._db["tracked_wallets"].update_one(
                        {"address": f_user.address, "chain": "solana"},
                        {
                            "$set": {
                                "address": f_user.address,
                                "chain": "solana",
                                "fomo_id": f_user.id,
                                "fomo_handle": f_user.user_handle,
                                "display_name": f_user.display_name,
                                "source": "fomo_following_expansion",
                                "tier": tier,
                                "peer_endorsement_count": endorsement_count,
                                "endorsed_by": endorsed_by,
                                "score": score,
                                "pnl24h": f_user.pnl24h,
                                "total_volume": f_user.total_volume,
                                "badge": f_user.badge,
                                "is_active": True,
                                "updated_at": now,
                            },
                            "$setOnInsert": {
                                "created_at": now,
                            },
                        },
                        upsert=True,
                    )
                    solana_count += 1
                except Exception as e:
                    logger.error(
                        "roster_crawler.db_save_solana_failed",
                        extra={"address": f_user.address, "error": str(e)},
                    )

            # Upsert EVM address if present
            if f_user.evm_address and self._db is not None:
                try:
                    await self._db["tracked_wallets"].update_one(
                        {"address": f_user.evm_address, "chain": "evm"},
                        {
                            "$set": {
                                "address": f_user.evm_address,
                                "chain": "evm",
                                "fomo_id": f_user.id,
                                "fomo_handle": f_user.user_handle,
                                "display_name": f_user.display_name,
                                "source": "fomo_following_expansion",
                                "tier": tier,
                                "peer_endorsement_count": endorsement_count,
                                "endorsed_by": endorsed_by,
                                "score": score,
                                "pnl24h": f_user.pnl24h,
                                "total_volume": f_user.total_volume,
                                "badge": f_user.badge,
                                "is_active": True,
                                "updated_at": now,
                            },
                            "$setOnInsert": {
                                "created_at": now,
                            },
                        },
                        upsert=True,
                    )
                    evm_count += 1
                except Exception as e:
                    logger.error(
                        "roster_crawler.db_save_evm_failed",
                        extra={"address": f_user.evm_address, "error": str(e)},
                    )

        return {
            "top_traders_scanned": len(top_traders),
            "unique_followed_users": len(followed_users_map),
            "solana_wallets_upserted": solana_count,
            "evm_wallets_upserted": evm_count,
        }
