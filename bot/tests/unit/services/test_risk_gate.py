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
