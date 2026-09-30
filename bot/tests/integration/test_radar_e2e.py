"""End-to-end simulation test for the Early Token Sniper & Smart Money Radar pipeline."""
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.chain.solana_listener import SolanaEventListener, SolanaSwapEvent
from app.services.consensus_engine import ConsensusEngine, WalletBuyEvent
from app.services.risk_gate import RiskGate, TokenAuditInput
from app.services.provenance_checker import ProvenanceChecker
from app.services.signal_scorer import SignalScorer, TokenSnapshot
from app.jobs.radar_alert_dispatcher import radar_alert_dispatcher_job


@pytest.mark.asyncio
async def test_radar_pipeline_e2e_simulation():
    # 1. Mock MongoDB Collections
    mock_db = MagicMock()
    wallets_col = MagicMock()
    signals_col = MagicMock()
    provenance_col = MagicMock()
    provenance_col.find_one = AsyncMock(return_value=None)
    provenance_col.update_one = AsyncMock()

    stored_signals = {}

    async def mock_update_signal(filter_dict, update_dict, upsert=False):
        token = filter_dict.get("token_mint") or filter_dict.get("_id")
        if token not in stored_signals:
            stored_signals[token] = {"_id": token, **filter_dict}
        if "$set" in update_dict:
            stored_signals[token].update(update_dict["$set"])
        return MagicMock(acknowledged=True)

    signals_col.update_one = AsyncMock(side_effect=mock_update_signal)

    def mock_find_signals(query):
        cursor = MagicMock()
        score_min = query.get("score", {}).get("$gte", 0)
        matching = [
            doc for doc in stored_signals.values()
            if doc.get("score", 0) >= score_min and not doc.get("dispatched")
        ]
        cursor.to_list = AsyncMock(return_value=matching)
        return cursor

    signals_col.find = MagicMock(side_effect=mock_find_signals)

    def get_collection(name):
        if name == "token_signals":
            return signals_col
        if name == "wallet_provenance":
            return provenance_col
        return wallets_col

    mock_db.__getitem__.side_effect = get_collection

    # 2. Setup Tracked Smart Wallets in Memory / Listener
    w1 = "SolSmartWalletAlpha11111111111111111111111"
    w2 = "SolSmartWalletBeta22222222222222222222222"
    tracked_wallets = {w1, w2}

    # 3. Simulate Swaps from Solana Listener
    token_mint = "PumpTokenMoonRocket1111111111111111111111"
    now = time.time()
    token_launch_time = now - 45.0  # 45s ago (ultra early <= 60s)

    consensus_engine = ConsensusEngine(db=mock_db, window_seconds=60)
    swaps_received = []

    async def on_swap_received(event: SolanaSwapEvent):
        swaps_received.append(event)
        score = 90.0 if event.user_wallet == w1 else 85.0
        buy_event = WalletBuyEvent(
            token_mint=event.mint,
            wallet_address=event.user_wallet,
            wallet_score=score,
            timestamp=event.timestamp,
            amount_usd=event.amount_usd,
            launch_timestamp=token_launch_time,
        )
        return await consensus_engine.add_buy(buy_event)

    listener = SolanaEventListener(
        ws_url="wss://mock",
        tracked_wallets=tracked_wallets,
        on_swap_callback=on_swap_received,
    )

    # Stream Swap 1: W1 buys $3,000 on Pump.fun
    await listener.handle_log_notification({
        "signature": "sig_swap_w1",
        "err": None,
        "logs": [
            "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]",
            "Program log: Instruction: Buy",
            f"Program data: user={w1} mint={token_mint} sol_amount=20000000000",
            "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success",
        ],
    })

    # Stream Swap 2: W2 buys $1,500 on Pump.fun 15s later
    signal = await listener.handle_log_notification({
        "signature": "sig_swap_w2",
        "err": None,
        "logs": [
            "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]",
            "Program log: Instruction: Buy",
            f"Program data: user={w2} mint={token_mint} sol_amount=10000000000",
            "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success",
        ],
    })

    # 4. Assert Consensus Cluster Detected
    assert len(swaps_received) == 2
    assert token_mint in stored_signals
    assert stored_signals[token_mint]["is_consensus"] is True
    # Conviction: 0.9^2 + 0.85^2 = 0.81 + 0.7225 = 1.5325 >= 1.3
    assert stored_signals[token_mint]["conviction"] > 1.5
    assert pytest.approx(stored_signals[token_mint]["earlyness"], 0.02) == 0.99  # launched 45s ago

    # 5. Check Anti-Sybil Provenance
    mock_rpc = MagicMock()
    mock_rpc.get_initial_funder = AsyncMock(side_effect=lambda w: f"IndependentFunder_{w}")
    provenance_checker = ProvenanceChecker(rpc_client=mock_rpc, db=mock_db)
    prov_result = await provenance_checker.check_cluster_provenance([w1, w2])
    assert prov_result.is_sybil is False

    # 6. Evaluate Hard Risk Gate
    audit = TokenAuditInput(
        mint_authority=None,
        freeze_authority=None,
        lp_locked_or_burned_ratio=1.0,
        sell_tax_pct=0.0,
        top_10_holder_share=0.15,
        deployer_rug_count=0,
    )
    risk_result = RiskGate.evaluate_audit(audit)
    assert risk_result.risk_passed is True

    # 7. Composite Signal Scorer
    scorer = SignalScorer(db=mock_db)
    snapshot = TokenSnapshot(
        token_mint=token_mint,
        token_name="Moon Rocket",
        token_symbol="ROCKET",
        chain="solana",
        risk_passed=risk_result.risk_passed,
        heat_normalized=0.95,
        volume_acceleration=0.85,
        security_rating=1.0,
        liquidity_depth=0.75,
        fomo_social_heat=0.80,
        wallets=[w1, w2],
        conviction=stored_signals[token_mint]["conviction"],
        age_seconds=45.0,
    )
    scored = await scorer.score_and_save(snapshot)
    assert scored.score >= 80
    assert scored.tier == "A_GRADE_SNIPER"
    assert stored_signals[token_mint]["score"] == scored.score

    # 8. Dispatch Telegram Alert
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.admin_chat_id = "987654"

    with patch("app.jobs.radar_alert_dispatcher.get_db", return_value=mock_db), \
         patch("app.jobs.radar_alert_dispatcher.get_settings", return_value=mock_settings), \
         patch("app.jobs.radar_alert_dispatcher.get_fomo_subscribed_chats", return_value={987654}):

        await radar_alert_dispatcher_job(context)

        # Assert Telegram message sent with formatted template and buttons
        context.bot.send_message.assert_called_once()
        msg_kwargs = context.bot.send_message.call_args.kwargs
        assert msg_kwargs["chat_id"] == 987654
        assert "SMART MONEY CONSENSUS DETECTED" in msg_kwargs["text"]
        assert token_mint in msg_kwargs["text"]
        assert msg_kwargs["reply_markup"] is not None

        # Assert marked as dispatched in database
        assert stored_signals[token_mint]["dispatched"] is True
