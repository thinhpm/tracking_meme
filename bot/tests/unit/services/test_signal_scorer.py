import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from app.services.signal_scorer import SignalScorer, TokenSnapshot, ScoredSignal


@pytest.fixture
def mock_db():
    db = MagicMock()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    db.__getitem__.return_value = collection
    return db


def test_compute_signal_score_when_risk_failed():
    scorer = SignalScorer()
    snapshot = TokenSnapshot(
        token_mint="RiskFailedToken",
        token_name="ScamToken",
        token_symbol="SCAM",
        chain="solana",
        risk_passed=False,
        heat_normalized=0.9,
        volume_acceleration=0.8,
        security_rating=0.9,
        liquidity_depth=0.8,
        fomo_social_heat=0.7,
        wallets=["W1", "W2"],
        conviction=2.0,
        age_seconds=120,
    )
    scored = scorer.compute_score(snapshot)
    assert isinstance(scored, ScoredSignal)
    assert scored.score == 0
    assert scored.tier == "IGNORE"


def test_compute_signal_score_a_grade_sniper():
    scorer = SignalScorer()
    snapshot = TokenSnapshot(
        token_mint="CleanToken777",
        token_name="Pepe Solana",
        token_symbol="PEPE",
        chain="solana",
        risk_passed=True,
        heat_normalized=0.90,       # 30% * 90 = 27
        volume_acceleration=0.80,   # 25% * 80 = 20
        security_rating=1.0,        # 20% * 100 = 20
        liquidity_depth=0.70,       # 15% * 70 = 10.5
        fomo_social_heat=0.80,      # 10% * 80 = 8.0
        # Total = 27 + 20 + 20 + 10.5 + 8.0 = 85.5 -> 85
        wallets=["W1", "W2", "W3"],
        conviction=2.5,
        age_seconds=180,
    )
    scored = scorer.compute_score(snapshot)
    assert scored.score == 85
    assert scored.tier == "A_GRADE_SNIPER"


@pytest.mark.asyncio
async def test_score_and_save_to_mongodb(mock_db):
    scorer = SignalScorer(db=mock_db)
    snapshot = TokenSnapshot(
        token_mint="TokenToSave123",
        token_name="Alpha Meme",
        token_symbol="ALPHA",
        chain="solana",
        risk_passed=True,
        heat_normalized=0.85,
        volume_acceleration=0.75,
        security_rating=0.95,
        liquidity_depth=0.60,
        fomo_social_heat=0.70,
        wallets=["W1", "W2"],
        conviction=1.8,
        age_seconds=60,
    )
    scored = await scorer.score_and_save(snapshot)

    assert scored.score == 79
    assert scored.tier == "WATCHLIST"

    mock_db["token_signals"].update_one.assert_called_once()
    filter_arg, update_arg = mock_db["token_signals"].update_one.call_args[0]
    assert filter_arg == {"token_mint": "TokenToSave123"}
    assert update_arg["$set"]["score"] == 79
    assert update_arg["$set"]["tier"] == "WATCHLIST"
