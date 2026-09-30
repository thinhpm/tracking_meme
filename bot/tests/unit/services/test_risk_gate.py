import pytest
from app.services.risk_gate import RiskGate, TokenAuditInput, RiskGateResult


def test_clean_token_passes_risk_gate():
    audit_input = TokenAuditInput(
        mint_authority=None,
        freeze_authority=None,
        lp_locked_or_burned_ratio=0.95,  # 95% >= 80%
        sell_tax_pct=0.0,                # 0% <= 15%
        top_10_holder_share=0.20,        # 20% < 35%
        deployer_rug_count=0,
    )
    result = RiskGate.evaluate_audit(audit_input)
    assert isinstance(result, RiskGateResult)
    assert result.risk_passed is True
    assert result.reason is None


def test_mint_authority_fails():
    audit_input = TokenAuditInput(
        mint_authority="SomeActiveAuthorityAddress",
        freeze_authority=None,
        lp_locked_or_burned_ratio=1.0,
        sell_tax_pct=0.0,
    )
    result = RiskGate.evaluate_audit(audit_input)
    assert result.risk_passed is False
    assert "mint_authority" in result.reason


def test_freeze_authority_fails():
    audit_input = TokenAuditInput(
        mint_authority=None,
        freeze_authority="ActiveFreezeAuth123",
        lp_locked_or_burned_ratio=1.0,
        sell_tax_pct=0.0,
    )
    result = RiskGate.evaluate_audit(audit_input)
    assert result.risk_passed is False
    assert "freeze_authority" in result.reason


def test_low_lp_locked_fails():
    audit_input = TokenAuditInput(
        mint_authority=None,
        freeze_authority=None,
        lp_locked_or_burned_ratio=0.70,  # 70% < 80%
        sell_tax_pct=0.0,
    )
    result = RiskGate.evaluate_audit(audit_input)
    assert result.risk_passed is False
    assert "lp_locked_or_burned" in result.reason


def test_high_sell_tax_fails():
    audit_input = TokenAuditInput(
        mint_authority=None,
        freeze_authority=None,
        lp_locked_or_burned_ratio=1.0,
        sell_tax_pct=25.0,  # 25% > 15%
    )
    result = RiskGate.evaluate_audit(audit_input)
    assert result.risk_passed is False
    assert "sell_tax" in result.reason


def test_check_pool_silence():
    from app.services.risk_gate import check_pool_silence

    # Case 1: Healthy pool with buys and sells -> PASS
    passed, reason = check_pool_silence(buys_24h=50, sells_24h=20, pool_age_seconds=1200)
    assert passed is True

    # Case 2: Pool is very young (3 minutes old) with 10 buys and 0 sells -> wait time not reached yet -> PASS
    passed, reason = check_pool_silence(buys_24h=10, sells_24h=0, pool_age_seconds=180)
    assert passed is True

    # Case 3: Pool is 35 minutes old (2100s) with 8 buys and 0 sells -> wait time 1800s reached -> FAIL (Honeypot)
    passed, reason = check_pool_silence(buys_24h=8, sells_24h=0, pool_age_seconds=2100)
    assert passed is False
    assert "HONEYPOT_POOL_SILENCE" in reason

    # Case 4: Heavy buying (80 buys) and 0 sells after 15m (900s >= floor 600s) -> FAIL (Honeypot)
    passed, reason = check_pool_silence(buys_24h=80, sells_24h=0, pool_age_seconds=900)
    assert passed is False
    assert "HONEYPOT_POOL_SILENCE" in reason

    # Case 5: Cohort sold override -> Even if 0 pool sells, tracked smart money sold -> PASS
    passed, reason = check_pool_silence(buys_24h=80, sells_24h=0, pool_age_seconds=900, cohort_sold=True)
    assert passed is True
    assert "cohort_sold_verified" in reason


def test_risk_gate_honeypot_pool_silence_fails():
    audit_input = TokenAuditInput(
        mint_authority=None,
        freeze_authority=None,
        lp_locked_or_burned_ratio=1.0,
        sell_tax_pct=0.0,
        buys_24h=20,
        sells_24h=0,
        pool_age_seconds=2500,  # > 30m with 0 sells
    )
    result = RiskGate.evaluate_audit(audit_input)
    assert result.risk_passed is False
    assert "pool_silence" in result.reason

