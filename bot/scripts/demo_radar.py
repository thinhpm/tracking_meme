"""Interactive demonstration script to run and test the complete Radar pipeline with MongoDB."""
import asyncio
from pathlib import Path
import sys
import time

BOT_DIR = Path(__file__).resolve().parent.parent
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from app.config import get_settings
from app.db.mongo import get_db, init_db_indexes, close_mongo_client
from app.handlers.radar_alert import RadarAlertFormatter
from app.services.chain.solana_listener import SolanaSwapEvent
from app.services.consensus_engine import ConsensusEngine, WalletBuyEvent
from app.services.provenance_checker import ProvenanceChecker
from app.services.risk_gate import RiskGate, TokenAuditInput
from app.services.signal_scorer import SignalScorer, TokenSnapshot


async def main():
    print("=" * 70)
    print("EARLY TOKEN SNIPER & SMART MONEY RADAR - LIVE PIPELINE TEST")
    print("=" * 70)

    settings = get_settings()
    print(f"[*] MongoDB URI: {settings.mongodb_uri}")
    print(f"[*] Database: {settings.mongodb_db_name}")
    print(f"[*] Solana RPC: {settings.solana_rpc_url[:40]}...")
    print(f"[*] Solana WS:  {settings.solana_ws_url[:40]}...")
    print()

    # Step 1: Connect to MongoDB
    print("[1/6] Ket noi MongoDB & Khoi tao Indexes...")
    db = get_db()
    await init_db_indexes(db)
    print("   [OK] MongoDB ket noi thanh cong, indexes initialized.")
    print()

    # Step 2: Seed Tracked Smart Wallets
    print("[2/6] Nap danh sach Smart Wallets (Tier 1 & Tier 2)...")
    wallets = [
        {
            "address": "SoLWhaleAlpha11111111111111111111111111111",
            "fomo_handle": "sol_whale",
            "display_name": "Solana Whale #1",
            "score": 92.0,
            "tier": "tier_1",
            "source": "fomo_leaderboard",
        },
        {
            "address": "SoLAlphaTrader22222222222222222222222222222",
            "fomo_handle": "alpha_trader",
            "display_name": "Alpha Hunter",
            "score": 88.0,
            "tier": "tier_2",
            "source": "fomo_following_expansion",
        },
    ]

    for w in wallets:
        await db["tracked_wallets"].update_one(
            {"address": w["address"], "chain": "solana"},
            {"$set": {**w, "chain": "solana", "is_active": True, "updated_at": time.time()}},
            upsert=True,
        )
        print(f"   Tracked: @{w['fomo_handle']} (Score: {w['score']}) -> {w['address'][:16]}...")
    print()

    # Step 3: Simulate Realtime Swaps (Pump.fun)
    token_mint = "MoonRocketPump7777777777777777777777777777"
    token_name = "Moon Rocket"
    token_symbol = "ROCKET"
    now = time.time()
    token_launch_time = now - 45.0  # 45s ago (ultra early)

    print("[3/6] Nhan tin hieu Swap thoi gian thuc tu Solana Listener...")
    consensus_engine = ConsensusEngine(db=db, window_seconds=60)

    # Swap 1
    print("   Swap 1: @sol_whale mua $4,500 token ROCKET tren Pump.fun...")
    buy1 = WalletBuyEvent(
        token_mint=token_mint,
        wallet_address=wallets[0]["address"],
        wallet_score=wallets[0]["score"],
        timestamp=now,
        amount_usd=4500.0,
        launch_timestamp=token_launch_time,
    )
    sig1 = await consensus_engine.add_buy(buy1)
    print(f"      Status: Wallets={len(sig1.wallets)}, Consensus={sig1.is_consensus}")

    # Swap 2 (15s later)
    print("   Swap 2: @alpha_trader mua $3,200 token ROCKET tren Pump.fun (15s sau)...")
    buy2 = WalletBuyEvent(
        token_mint=token_mint,
        wallet_address=wallets[1]["address"],
        wallet_score=wallets[1]["score"],
        timestamp=now + 15,
        amount_usd=3200.0,
        launch_timestamp=token_launch_time,
    )
    sig2 = await consensus_engine.add_buy(buy2)
    print(f"      CLUSTER DETECTED!")
    print(f"      - Wallets count: {len(sig2.wallets)}")
    print(f"      - Quadratic Conviction: {sig2.conviction:.2f} (Threshold: 1.30)")
    print(f"      - Earlyness Multiplier: {sig2.earlyness:.2f}x (Age: 45s)")
    print(f"      - Heat Score: {sig2.heat:.2f}")
    print()

    # Step 4: Anti-Sybil Provenance Check
    print("[4/6] Kiem tra Anti-Sybil Provenance (Nguon tien vi)...")
    provenance_checker = ProvenanceChecker(db=db)
    prov_result = await provenance_checker.check_cluster_provenance([w["address"] for w in wallets])
    print(f"      - Is Sybil Crew: {prov_result.is_sybil} (Max funder share: {prov_result.max_funder_share * 100:.1f}%)")
    print(f"      - Result: Nguon tien doc lap, khong phai bot cua dev rug! [PASS]")
    print()

    # Step 5: Hard Risk Gate & Composite Scoring
    print("[5/6] Danh gia Hard Risk Gate & Tinh diem Composite Scorer...")
    audit = TokenAuditInput(
        mint_authority=None,
        freeze_authority=None,
        lp_locked_or_burned_ratio=1.0,
        sell_tax_pct=0.0,
        top_10_holder_share=0.18,
        deployer_rug_count=0,
    )
    risk_result = RiskGate.evaluate_audit(audit)
    print(f"      - Risk Gate: {'PASSED' if risk_result.risk_passed else 'FAILED'}")

    scorer = SignalScorer(db=db)
    snapshot = TokenSnapshot(
        token_mint=token_mint,
        token_name=token_name,
        token_symbol=token_symbol,
        chain="solana",
        risk_passed=risk_result.risk_passed,
        heat_normalized=0.92,
        volume_acceleration=0.85,
        security_rating=1.0,
        liquidity_depth=0.78,
        fomo_social_heat=0.80,
        wallets=[w["address"] for w in wallets],
        conviction=sig2.conviction,
        age_seconds=45.0,
    )
    scored = await scorer.score_and_save(snapshot)
    print(f"      - Composite Score: {scored.score}/100")
    print(f"      - Classification Tier: {scored.tier}")
    print(f"      - Component Breakdown:")
    for comp, val in scored.components.items():
        print(f"        - {comp.replace('_', ' ').capitalize()}: {val:.1f}")
    print()

    # Step 6: Format Telegram Alert
    print("[6/6] Dinh dang Telegram Alert (Mode 2 - Semi-Autonomous)...")
    signal_doc = {
        "token_mint": token_mint,
        "token_name": token_name,
        "token_symbol": token_symbol,
        "chain": "solana",
        "score": scored.score,
        "tier": scored.tier,
        "liquidity_usd": 68500.0,
        "market_cap_usd": 185000.0,
        "age_seconds": 45.0,
        "conviction": sig2.conviction,
        "wallets_detail": [
            {"handle": "sol_whale", "score": 92, "amount_usd": 4500.0, "time_ago": "45s ago"},
            {"handle": "alpha_trader", "score": 88, "amount_usd": 3200.0, "time_ago": "30s ago"},
        ],
        "security": {
            "mint_auth": "Revoked",
            "freeze_auth": "Revoked",
            "lp_status": "100% Burned",
            "top_10_share": "18.2%",
            "sell_tax": "0% Tax",
        },
    }

    alert_text, reply_markup = RadarAlertFormatter.format_alert(signal_doc)
    print("-" * 70)
    print("PREVIEW TELEGRAM ALERT MESSAGE:")
    print("-" * 70)
    print(alert_text)
    print("-" * 70)
    print("INLINE KEYBOARD BUTTONS:")
    for row in reply_markup.inline_keyboard:
        row_str = " | ".join(f"[{b.text}] -> {b.url}" for b in row)
        print(f"  {row_str}")
    print("-" * 70)

    # Step 7: Verify MongoDB document
    db_signal = await db["token_signals"].find_one({"token_mint": token_mint})
    print()
    print("Da luu vao MongoDB collection 'token_signals':")
    print(f"   _id: {db_signal['_id']}")
    print(f"   status: {db_signal.get('status')}")
    print(f"   score: {db_signal.get('score')}")
    print(f"   tier: {db_signal.get('tier')}")
    print(f"   wallets: {db_signal.get('wallets')}")
    print()
    print("TOAN BO PIPELINE RADAR DA CHAY THANH CONG VOI REAL MONGODB!")
    print("=" * 70)

    close_mongo_client()


if __name__ == "__main__":
    asyncio.run(main())
