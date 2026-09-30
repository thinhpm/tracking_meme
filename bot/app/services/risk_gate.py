"""Hard risk gate filter evaluating honeypot, mint/freeze authorities, and LP lock status."""
from __future__ import annotations

import logging
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)

DEFAULT_SILENCE_MIN_BUYS = 8
DEFAULT_SILENCE_MIN_AGE_S = 1800.0  # 30m
DEFAULT_SILENCE_FLOOR_S = 600.0     # 10m


def calculate_silence_wait_s(
    buys: int,
    min_buys: int = DEFAULT_SILENCE_MIN_BUYS,
    full_s: float = DEFAULT_SILENCE_MIN_AGE_S,
    floor_s: float = DEFAULT_SILENCE_FLOOR_S,
) -> float:
    """Computes dynamic wait time before 0 sells qualifies as a honeypot."""
    if buys <= 0:
        return full_s
    return max(floor_s, min(full_s, full_s * min_buys / buys))


def check_pool_silence(
    buys_24h: int,
    sells_24h: int,
    pool_age_seconds: float | None = None,
    cohort_sold: bool = False,
    min_buys: int = DEFAULT_SILENCE_MIN_BUYS,
) -> tuple[bool, str]:
    """Evaluates whether the pool exhibits honeypot behavior (zero sells after significant buys/time)."""
    if cohort_sold:
        return True, "cohort_sold_verified"

    if sells_24h > 0:
        return True, f"{sells_24h} sells recorded"

    if buys_24h >= min_buys and pool_age_seconds is not None:
        wait_s = calculate_silence_wait_s(buys_24h, min_buys=min_buys)
        if pool_age_seconds >= wait_s:
            return (
                False,
                f"HONEYPOT_POOL_SILENCE: {buys_24h} buys and 0 sells after {int(pool_age_seconds // 60)}m (wait threshold: {int(wait_s // 60)}m)",
            )

    return True, "insufficient_silence_evidence"


class TokenAuditInput(NamedTuple):
    mint_authority: str | None = None
    freeze_authority: str | None = None
    lp_locked_or_burned_ratio: float = 1.0  # 0.0 to 1.0
    sell_tax_pct: float = 0.0               # percentage, e.g. 5.0 = 5%
    top_10_holder_share: float = 0.20       # 0.0 to 1.0
    deployer_rug_count: int = 0
    buys_24h: int | None = None
    sells_24h: int | None = None
    pool_age_seconds: float | None = None
    cohort_sold: bool = False


class RiskGateResult(NamedTuple):
    risk_passed: bool
    reason: str | None
    details: dict[str, Any]


class RiskGate:
    """Evaluates non-negotiable security requirements for newly surfaced tokens."""

    @staticmethod
    def evaluate_audit(audit: TokenAuditInput) -> RiskGateResult:
        """Fast-fails on the first failed security parameter."""
        details = {
            "mint_authority": audit.mint_authority,
            "freeze_authority": audit.freeze_authority,
            "lp_locked_or_burned_ratio": audit.lp_locked_or_burned_ratio,
            "sell_tax_pct": audit.sell_tax_pct,
            "top_10_holder_share": audit.top_10_holder_share,
            "deployer_rug_count": audit.deployer_rug_count,
            "buys_24h": audit.buys_24h,
            "sells_24h": audit.sells_24h,
            "pool_age_seconds": audit.pool_age_seconds,
            "cohort_sold": audit.cohort_sold,
        }


        # 1. Mint authority check
        if audit.mint_authority:
            return RiskGateResult(
                risk_passed=False,
                reason="mint_authority_active",
                details=details,
            )

        # 2. Freeze authority check
        if audit.freeze_authority:
            return RiskGateResult(
                risk_passed=False,
                reason="freeze_authority_active",
                details=details,
            )

        # 3. Liquidity lock / burn check (>= 80%)
        if audit.lp_locked_or_burned_ratio < 0.80:
            return RiskGateResult(
                risk_passed=False,
                reason="lp_locked_or_burned_below_threshold",
                details=details,
            )

        # 4. Sell tax check (<= 15%)
        if audit.sell_tax_pct > 15.0:
            return RiskGateResult(
                risk_passed=False,
                reason="sell_tax_exceeds_threshold",
                details=details,
            )

        # 5. Top 10 non-DEX holders share (< 35%)
        if audit.top_10_holder_share >= 0.35:
            return RiskGateResult(
                risk_passed=False,
                reason="top_10_holders_concentration_too_high",
                details=details,
            )

        # 6. Deployer reputation (< 2 rugs)
        if audit.deployer_rug_count >= 2:
            return RiskGateResult(
                risk_passed=False,
                reason="deployer_has_prior_rugs",
                details=details,
            )

        # 7. Pool silence / honeypot check
        if audit.buys_24h is not None and audit.sells_24h is not None:
            silence_passed, silence_reason = check_pool_silence(
                buys_24h=audit.buys_24h,
                sells_24h=audit.sells_24h,
                pool_age_seconds=audit.pool_age_seconds,
                cohort_sold=audit.cohort_sold,
            )
            if not silence_passed:
                return RiskGateResult(
                    risk_passed=False,
                    reason=f"honeypot_pool_silence: {silence_reason}",
                    details=details,
                )

        return RiskGateResult(
            risk_passed=True,
            reason=None,
            details=details,
        )

