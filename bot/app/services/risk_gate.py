"""Hard risk gate filter evaluating honeypot, mint/freeze authorities, and LP lock status."""
from __future__ import annotations

import logging
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class TokenAuditInput(NamedTuple):
    mint_authority: str | None = None
    freeze_authority: str | None = None
    lp_locked_or_burned_ratio: float = 1.0  # 0.0 to 1.0
    sell_tax_pct: float = 0.0               # percentage, e.g. 5.0 = 5%
    top_10_holder_share: float = 0.20       # 0.0 to 1.0
    deployer_rug_count: int = 0


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

        return RiskGateResult(
            risk_passed=True,
            reason=None,
            details=details,
        )
