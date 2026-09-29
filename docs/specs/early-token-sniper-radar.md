# Feature: Early Token Sniper & Smart Money Radar Platform

## Objective

Build an autonomous **Smart Money Radar & Early Token Sniper** platform inspired by Fomo's social trading intelligence and open-source on-chain radar mechanics (e.g. `fomo-robinhood-radar`). 

The platform separates discovery, intelligence, and execution into clean decoupled stages:
1. **Metadata Seed:** Harvests high-performing traders from Fomo without burning API quotas (via Headless Privy Auth or 3rd-party metadata sync).
2. **Wallet Resolution:** Unmasks real on-chain execution wallets from platform profiles via temporal swap correlation.
3. **Real-time On-Chain Ingest:** Continuously monitors on-chain DEX swaps, new liquidity pools, and wallet fills via RPC/WebSocket streams.
4. **Smart Money & Consensus Engine:** Tracks wallet clusters, weighted conviction scores, and earlyness metrics.
5. **Anti-Sybil & Provenance Filter:** Filters out fake volume, seeded wallets, and developer crews.
6. **Pre-Scoring Risk Gate:** Executes instant honeypot/sell simulations and authority checks before scoring.
7. **Signal Scorer & Execution Gate:** Evaluates composite scores (0–100) and routes qualified signals through 3 operational modes (Research, Semi-Auto Telegram Alert with 1-Click Buy, and Autonomous Snipe).
8. **Feedback Loop:** Logs all features, entry/exit prices, and PnL to iteratively train statistical and ML scoring models.

---

## Target Users

- **Quantitative Memecoin Traders:** Seeking high-conviction early entries backed by verified smart money consensus rather than noisy social chatter.
- **Telegram Bot Subscribers:** Receiving actionable real-time alerts with direct execution buttons and rich risk diagnostics.
- **Autonomous Algorithmic Trading Systems:** Executing sub-second buys on high-scoring early pool events via MEV-protected RPCs.

---

## Layer

- [x] Backend Core Services (`api` / `radar` / `engine`)
- [x] Telegram Bot Interface (`bot` service)
- [x] Headless Worker (`fomo_auth_worker`)
- [ ] Web Frontend Dashboard (Future phase)

---

## End-to-End System Architecture

```
                                  DATA SOURCES
                                       │
     ┌─────────────────────────────────┼─────────────────────────────────┐
     ▼                                 ▼                                 ▼
┌──────────────┐             ┌───────────────────┐             ┌───────────────────┐
│  Fomo Web    │             │   On-Chain DEX    │             │   DEX Indexers    │
│(Headless Auth│             │   (Solana / Base) │             │ (DexScreener, GMGN│
│  or 3rd-party│             │ WebSocket / RPC   │             │   GoPlus Security)│
└──────┬───────┘             └─────────┬─────────┘             └─────────┬─────────┘
       │                               │                                 │
       │ Seed (Roster / Profiles)      │ Real-time Events (Swaps, Pools) │ Price / Security
       ▼                               ▼                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             INGESTION & DATA LAYER                               │
│                                                                                  │
│ 1. Wallet Resolver: Correlates Fomo trader swaps (±90s) → On-Chain Wallets        │
│ 2. Canonical Event Bus (Redis / In-Memory Queue): Normalized swap & pool events  │
│ 3. Document Database (MongoDB): Tracked Wallets, Signals, Positions, Ledger       │
└──────────────────────────────────────┬───────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            INTELLIGENCE & SIGNAL CORE                            │
│                                                                                  │
│ ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐   │
│ │ Smart Money Engine   │   │ Earlyness Engine     │   │ Anti-Sybil / Crews   │   │
│ │ - Win rate & ROI     │   │ - Age vs Pool Open   │   │ - Seeded Wallets     │   │
│ │ - Conviction Score   │   │ - Time-decay weight  │   │ - Common Funder Tree │   │
│ │ - Cluster Detection  │   │   (1.0x → 0.5x → 0.1)│   │ - Dev Crew Pattern   │   │
│ └──────────┬───────────┘   └──────────┬───────────┘   └──────────┬───────────┘   │
│            └──────────────────────────┼──────────────────────────┘               │
│                                       ▼                                          │
│ ┌────────────────────────────────────────────────────────────────────────────┐   │
│ │ Hard Risk Filter (Pass / Fail): Honeypot, Mint/Freeze Auth, LP Lock        │   │
│ └─────────────────────────────────────┬──────────────────────────────────────┘   │
│                                       ▼                                          │
│ ┌────────────────────────────────────────────────────────────────────────────┐   │
│ │ Composite Scorer (0 - 100):                                                │   │
│ │ Score = SmartMoney(30%) + Momentum(25%) + Safety(20%) + LP(15%) + Social(10%) │
│ └────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬───────────────────────────────────────────┘
                                       │
                         Threshold-based Routing Gate
                                       │
       ┌───────────────────────────────┼───────────────────────────────┐
       ▼                               ▼                               ▼
 [Score 60 - 79]                 [Score 80 - 89]                 [Score ≥ 90]
  Mode 1: Research                Mode 2: Semi-Auto               Mode 3: Autonomous
┌──────────────────┐            ┌──────────────────┐            ┌──────────────────┐
│ - Log to DB      │            │ - Telegram Alert │            │ - MEV Private RPC│
│ - Watchlist pool │            │ - 1-Click Buy Btn│            │ - Auto Snipe Buy │
│ - Monitor heat   │            │ - Slippage modal │            │ - TP/SL Manager  │
└──────────────────┘            └──────────────────┘            └────────┬─────────┘
                                                                         │
                                                                         ▼
                                                                ┌──────────────────┐
                                                                │ FEEDBACK LOOP    │
                                                                │ - Trade Ledger   │
                                                                │ - Post-Mortem PnL│
                                                                │ - Model Retrain  │
                                                                └──────────────────┘
```

---

## Core Features & Acceptance Criteria

| # | Subsystem | Feature | Acceptance Criteria |
|---|---|---|---|
| 1 | **Data Layer** | **Quota-Free Fomo Ingest** | `fomo_auth_worker` refreshes Privy tokens every 45m; syncs top 100 traders without consuming 3rd-party API credits. Supports static 3rd-party API key as fallback. |
| 2 | **Social Graph**| **Top Trader Following Network** | Crawls `/v2/users/{user_id}/followingPaginate` for top leaderboard traders. Extracts Solana (`address`), EVM (`evmAddress`), and computes `peer_endorsement_count` to expand smart money coverage. |
| 3 | **Resolver** | **Fomo-to-Wallet Resolver** | Reconstructs true execution wallet addresses by correlating Fomo activity against on-chain block swaps within a $\pm 90$s window. Must achieve $\ge 95\%$ confidence before whitelisting. |
| 4 | **Ingest** | **Real-time Chain Listener** | WebSocket / RPC listener on Solana (Raydium / Pump.fun) and EVM (Uniswap / Robinhood chain) captures swaps and pool launches with $< 500\text{ms}$ latency. |
| 5 | **Intelligence**| **Smart Money Scoring** | Scores tracked wallets based on 30-day Win Rate, Median ROI, Early Entry ratio, and Rug Exposure (0–100 scale). |
| 6 | **Intelligence**| **Cluster Consensus** | Detects when 2+ distinct smart wallets (score $\ge 65$) buy the same token within a 60-second window. |
| 7 | **Intelligence**| **Conviction Metric** | Computes quadratic conviction $\sum (\text{score}/100)^2$. Distinguishes high-tier consensus from low-tier swarm buys. |
| 8 | **Intelligence**| **Earlyness Decay** | Multiplies signal heat by entry timing factor: $1.0\times$ within 60s of pool launch, $0.5\times$ at 30 min, $0.1\times$ at 10 hours. |
| 9 | **Anti-Sybil** | **Provenance & Seeded Filter**| Traces funding origins of buyer cohort. Automatically rejects signals if $\ge 40\%$ of buyers share a recent common funder (seeder address). |
| 10| **Risk Gate** | **Pre-Scoring Safety Filter** | Simulates token sellability, checks mint/freeze authorities, LP burned/locked percentage, and deployer past rug count. Any failure triggers immediate `REJECT`. |
| 11| **Scoring** | **Composite Signal Scorer** | Weighted algorithm: Smart Money (30%), Momentum (25%), Safety (20%), Liquidity (15%), Social (10%). Produces normalized 0–100 score. |
| 12| **Execution** | **Mode 1: Research & Watch**| Stores all candidate tokens with score $\ge 60$ in MongoDB for statistical backtesting. |
| 13| **Execution** | **Mode 2: Semi-Auto Telegram**| Formats and dispatches high-conviction alerts (score 80–89) with token summary, smart wallets involved, safety audit, and Telegram inline 1-click buy buttons. |
| 14| **Execution** | **Mode 3: Autonomous Sniper**| For score $\ge 90$: Submits private RPC buy transaction via Jito (Solana) or Flashbots (EVM) with customizable priority fee, max slippage, and duplicate buy guard. |
| 15| **Position** | **Position & Exit Manager** | Manages auto-sniped tokens: Multi-tier Take Profit (+50%, +100%, +300%), Trailing Stop (-20%), and Liquidity-Drain Panic Exit. |
| 16| **Feedback** | **Performance Ledger** | Records entry price, gas/priority fee, exit price, holding duration, and contributing features to evaluate signal quality over 1,000+ trades. |

---

## Detailed Engine Specifications

### 1. Ingestion, Social Graph & Wallet Resolution Engine (`services/resolver/`)

The platform expands its smart money roster using a **2-Tier Ingestion Strategy**:

```
Tier 1: Leaderboard Ingestion
   GET /v2/leaderboard?limit=50
            │
            ▼ Top 50 Traders
Tier 2: Social Graph Expansion
   GET /v2/users/{user_id}/followingPaginate
            │
            ├─► Solana `address` & EVM `evmAddress`
            ├─► `pnl24h`, `totalVolume`, `numTrades`, `badge`
            └─► Compute `peer_endorsement_count`
            │
            ▼
   MongoDB `tracked_wallets` (200 - 500 Curated Smart Wallets)
            │
            ▼
   Wallet Resolver (Correlates on-chain swap blocks ±90s for unconfirmed profiles)
```

#### Social Following Endpoint Contract (`/v2/users/{user_id}/followingPaginate`):
- Headers required:
  - `Authorization: Bearer <privy_token>`
  - `x-supported-chains: 1,56,143,4663,5042,8453,1399811149`
- Key Fields Extracted:
  - `id`: Internal user UUID
  - `address`: Direct Solana wallet address
  - `evmAddress`: Direct EVM wallet address
  - `userHandle`, `displayName`
  - `following`, `followers`, `swapCount`, `numTrades`, `totalVolume`, `pnl24h`
  - `badge`: e.g. `top_100_badge` with historical rank and all-time PnL.

```python
class WalletResolver:
    """Discovers real on-chain execution wallet for a Fomo trader."""

    async def resolve_trader_wallet(
        self,
        trader_handle: str,
        fomo_swaps: list[FomoSwap],
        chain: str,
    ) -> ResolutionResult:
        """
        1. Query on-chain block logs around each swap timestamp (±90s).
        2. Identify intersecting buyer addresses for the same token across ≥3 swaps.
        3. Score candidates by intersection frequency and amount similarity.
        4. If top candidate confidence >= 0.95:
               Save to `tracked_wallets` collection.
        """
```

### 2. Smart Money & Conviction Engine (`services/analytics/`)

#### Wallet Score Algorithm
$$\text{WalletScore} = 0.35 \cdot \text{WinRate} + 0.25 \cdot \text{NormROI} + 0.25 \cdot \text{EarlyRatio} + 0.15 \cdot \text{Consistency} - \text{RugPenalty}$$

#### Conviction & Cluster Algorithm
When token $T$ receives buys from wallets $W_1, W_2, \dots, W_k$ within time window $\Delta t \le 60\text{s}$:
$$\text{Conviction}(T) = \sum_{i=1}^{k} \left( \frac{\text{Score}(W_i)}{100} \right)^2$$
- If $k \ge 2$ and $\text{Conviction} \ge 1.3$, flag as **Smart Money Cluster**.

#### Earlyness Factor
$$\text{Earlyness}(\Delta t_{\text{launch}}) = 
\begin{cases} 
1.0 & \text{if } \Delta t_{\text{launch}} \le 60\text{s} \\
0.5 & \text{if } 60\text{s} < \Delta t_{\text{launch}} \le 30\text{m} \\
0.1 & \text{if } \Delta t_{\text{launch}} > 10\text{h}
\end{cases}$$

$$\text{Heat}(T) = \text{Conviction}(T) \times \text{Earlyness}(\Delta t_{\text{launch}})$$

### 3. Anti-Sybil & Provenance Filter (`services/safety/provenance.py`)

Prevents scam deployers from spoofing smart money consensus:
1. When a buyer cluster is detected, trace the last 3 funding hops for each wallet via RPC (`eth_getTransactionByHash` / `getSignaturesForAddress`).
2. Construct a directed funding graph:
   $$\text{FunderShare} = \frac{\max_{\text{funder}} \text{WalletsFundedBy}(\text{funder})}{k}$$
3. If $\text{FunderShare} \ge 0.40$ (i.e. $\ge 40\%$ of wallets share the same parent funder), label as **Seeded Sybil Crew** and drop the signal.

### 4. Hard Risk Gate (`services/safety/risk_gate.py`)

Before calculating composite scores, evaluate non-negotiable safety criteria:
- **Sell Simulation:** Simulate swap `token -> base_currency` via local RPC fork or GoPlus API. Must be sellable with $< 15\%$ total tax.
- **Authority Check (Solana):** `mint_authority == null` and `freeze_authority == null`.
- **Liquidity Lock:** At least $80\%$ of initial LP tokens must be burned or locked in a verified locker contract for $\ge 30$ days.
- **Top 10 Holders:** Cumulative share of top 10 non-DEX holders must be $< 35\%$.
- **Deployer Reputation:** Deployer address has created $< 2$ previously rugged tokens.

### 5. Composite Scoring Engine (`services/scoring/`)

```python
def compute_signal_score(token_data: TokenSnapshot) -> int:
    # 1. Check Hard Risk Gate
    if not token_data.risk_passed:
        return 0

    # 2. Weighted components (0 - 100)
    smart_money_score = token_data.heat_normalized * 100      # 30%
    momentum_score = token_data.volume_acceleration * 100    # 25%
    safety_score = token_data.security_rating * 100          # 20%
    liquidity_score = token_data.liquidity_depth * 100       # 15%
    social_score = token_data.fomo_social_heat * 100         # 10%

    final_score = int(
        0.30 * smart_money_score +
        0.25 * momentum_score +
        0.20 * safety_score +
        0.15 * liquidity_score +
        0.10 * social_score
    )
    return max(0, min(100, final_score))
```

---

## Operational Execution Modes

### Mode 1: Research & Backtesting (Score 60 - 79)
- Stores all token metrics, wallet entries, and subsequent 1h/24h price changes in the `paper_trades` table.
- Does not spam Telegram or trigger executions.

### Mode 2: Semi-Autonomous Telegram Alerts (Score 80 - 89)
Dispatches formatted alert to subscribed Telegram channels:

```
🚨 SMART MONEY CONSENSUS DETECTED (Score: 86/100)

🪙 Token: PEPE2 (Solana)
📋 CA: 7xKX...pump
💰 Liquidity: $84,500 | MC: $210,000
⏱ Age: 4 minutes (Earlyness: HIGH)

👥 Smart Money Cluster (3 Wallets):
• @sol_whale (Score 91) → $4,500 (3m ago)
• @alpha_trader (Score 84) → $3,200 (2m ago)
• @sniper_king (Score 78) → $2,100 (1m ago)
🔥 Conviction: 2.14 | Sybil Risk: 0% CLEAN

🛡 Security Audit:
✅ Mint Revoked | ✅ Freeze Revoked | ✅ LP Burned (98%)
✅ Honeypot Simulation: PASS (Tax: 0/0%)

[⚡ Quick Buy 0.5 SOL] [⚡ Quick Buy 1.0 SOL] [📈 View DexScreener]
```

### Mode 3: Autonomous Sniper Engine (Score ≥ 90)
When score reaches $\ge 90$ and risk gates pass:
1. **Execution Gate:** Check daily drawdowns, open position count ($< \text{MAX\_OPEN\_POSITIONS}$), and wallet SOL/EVM balance.
2. **Private Transaction Routing:** Submit transaction bundle via Jito Block Engine (Solana) or Flashbots Builder (Base/EVM) with dynamic priority tip to avoid front-running/MEV sandwich attacks.
3. **Position Initialization:** Store position in `active_positions` table with automated TP/SL triggers.
4. **Position Manager Daemon:**
   - TP1: Sell 40% at $+50\%$ ROI (derisk).
   - TP2: Sell 40% at $+150\%$ ROI.
   - Moonbag: Trailing stop at $-20\%$ from peak.
   - Emergency Exit: Liquidate 100% immediately if LP liquidity drops $> 30\%$ in under 60 seconds.

---

## Data Models & Collections (MongoDB)

All entities are persisted in MongoDB (via `motor` async driver in Python / `pymongo`).

### 1. Collection: `tracked_wallets`
Stores resolved smart money wallets, historical performance metrics, and funding provenance.

```json
{
  "_id": "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  // Wallet address as PK
  "chain": "solana",                                    // solana, base, bsc, monad
  "evm_address": "0x8cadc02cc0afde9b12b2bff78b5af8f82c604a1e",
  "source": "fomo_resolved",                            // fomo_resolved, fomo_following_expansion, manual
  "fomo_handle": "AviFelman",                           // Platform username
  "display_name": "AviFelman",
  "score": 88,                                          // 0 - 100
  "social_graph": {
    "peer_endorsement_count": 6,                        // Number of Top 100 traders following this wallet
    "followed_by_traders": ["wizardofsoho", "frankdegods", "boosted"],
    "pnl24h": 78885.45,
    "total_volume": 625129.4,
    "badge": "top_100_badge"
  },
  "metrics": {
    "win_rate": 0.74,
    "median_roi": 1.45,                                 // +145%
    "total_pnl_usd": 182400.0,
    "total_trades": 96,
    "early_entries_count": 41,
    "max_drawdown": 0.22,
    "rug_exposure_count": 0
  },
  "provenance": {
    "parent_funder": "3Kz...9Lp",
    "initial_funding_usd": 1500.0,
    "is_sybil_flagged": false
  },
  "last_active": ISODate("2026-09-29T09:30:00Z"),
  "created_at": ISODate("2026-09-20T00:00:00Z"),
  "updated_at": ISODate("2026-09-29T09:30:00Z")
}
```
**Indexes:**
- `{ "chain": 1, "score": -1 }` (Fetch top wallets per chain)
- `{ "fomo_handle": 1 }` (Sparse, lookup by Fomo profile)
- `{ "provenance.parent_funder": 1 }` (Fast anti-sybil crew lookups)

---

### 2. Collection: `token_signals`
Stores detected early token events, smart money consensus clusters, risk audits, and calculated scores.

```json
{
  "_id": ObjectId("66f91a2b8e4f1a0012345678"),
  "token_address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
  "chain": "solana",
  "pool_address": "8sL...pump",
  "token_metadata": {
    "name": "Pepe 2.0",
    "symbol": "PEPE2",
    "decimals": 6,
    "pool_opened_at": ISODate("2026-09-29T09:26:00Z"),
    "initial_liquidity_usd": 84500.0
  },
  "token_age_seconds": 240,                             // Age at detection
  "conviction_score": 2.14,
  "earlyness_factor": 1.0,                              // 1.0 (<60s) -> 0.5 (30m) -> 0.1 (10h)
  "composite_score": 86,                                // 0 - 100
  "score_breakdown": {
    "smart_money": 28,                                  // max 30
    "momentum": 22,                                     // max 25
    "safety": 18,                                       // max 20
    "liquidity": 13,                                    // max 15
    "social": 5                                         // max 10
  },
  "wallets_involved": [
    {
      "address": "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
      "fomo_handle": "unipcs",
      "wallet_score": 91,
      "buy_usd": 4500.0,
      "buy_timestamp": ISODate("2026-09-29T09:27:00Z"),
      "entry_delay_seconds": 60
    }
  ],
  "security_audit": {
    "risk_passed": true,
    "sellable": true,
    "buy_tax_pct": 0.0,
    "sell_tax_pct": 0.0,
    "mint_revoked": true,
    "freeze_revoked": true,
    "lp_burned_pct": 98.5,
    "top10_holder_pct": 21.4,
    "deployer_rugged_count": 0
  },
  "status": "alerted",                                  // research, alerted, sniped, rejected
  "created_at": ISODate("2026-09-29T09:30:00Z")
}
```
**Indexes:**
- `{ "token_address": 1, "chain": 1 }` (Deduplication)
- `{ "composite_score": -1, "created_at": -1 }` (Querying highest conviction signals)
- `{ "status": 1, "created_at": -1 }` (Routing & Alert queue)
- `{ "created_at": 1 }` with `expireAfterSeconds: 2592000` (30-day TTL for ephemeral signals)

---

### 3. Collection: `active_positions`
Tracks open positions entered by Mode 3 (Autonomous Sniper) or Mode 2 (Telegram 1-Click Buy).

```json
{
  "_id": ObjectId("66f91b3c8e4f1a0012345679"),
  "signal_id": ObjectId("66f91a2b8e4f1a0012345678"),
  "token_address": "7xKX...pump",
  "chain": "solana",
  "entry": {
    "cost_sol": 0.5,
    "cost_usd": 75.0,
    "tokens_bought": 12500000.0,
    "entry_price_usd": 0.000006,
    "tx_hash": "5N4r...sol",
    "timestamp": ISODate("2026-09-29T09:30:05Z")
  },
  "current": {
    "price_usd": 0.000009,
    "peak_price_usd": 0.0000105,
    "unrealized_pnl_pct": 50.0
  },
  "targets": {
    "tp1_executed": true,                              // 40% sold at +50%
    "tp2_executed": false,                             // 40% sold at +150%
    "remaining_tokens": 7500000.0
  },
  "status": "open",                                    // open, closing, closed
  "created_at": ISODate("2026-09-29T09:30:05Z"),
  "updated_at": ISODate("2026-09-29T09:35:00Z")
}
```
**Indexes:**
- `{ "status": 1 }` (Fast scan for Position Manager daemon)
- `{ "token_address": 1, "status": 1 }` (Prevent duplicate open positions on same token)

---

### 4. Collection: `performance_ledger`
Records completed trade outcomes, PnL, holding duration, and snapshots of input features for statistical analysis and machine learning feedback.

```json
{
  "_id": ObjectId("66f91d5e8e4f1a0012345680"),
  "signal_id": ObjectId("66f91a2b8e4f1a0012345678"),
  "token_address": "7xKX...pump",
  "chain": "solana",
  "entry": {
    "price_usd": 0.000006,
    "timestamp": ISODate("2026-09-29T09:30:05Z"),
    "priority_fee_sol": 0.001
  },
  "exit": {
    "price_usd": 0.000012,
    "timestamp": ISODate("2026-09-29T10:15:00Z"),
    "exit_reason": "tp2"                               // tp1, tp2, trailing_stop, panic_lp, manual
  },
  "realized_pnl_usd": 68.5,
  "roi_percent": 91.33,
  "holding_seconds": 2695,
  "features_snapshot": {                               // Preserved input features at trade entry
    "composite_score": 86,
    "conviction_score": 2.14,
    "smart_wallets_count": 3,
    "earlyness_factor": 1.0,
    "initial_liquidity_usd": 84500.0,
    "buy_pressure_ratio": 0.78
  },
  "created_at": ISODate("2026-09-29T10:15:05Z")
}
```
**Indexes:**
- `{ "roi_percent": -1 }` (Querying winning vs losing patterns)
- `{ "created_at": -1 }` (Historical timeline analysis)

---

## Phased Implementation Roadmap

```
PHASE 1: Radar & Alerts MVP (Current Phase)
├── MongoDB Integration (motor client, collections & index init)
├── Fomo Headless Auth Worker (spec: fomo-headless-auth.md)
├── Fomo Trader Resolver (±90s swap correlator)
├── Solana On-Chain WebSocket Ingest (Raydium / Pump.fun)
├── Wallet Consensus & Conviction Calculator
├── Anti-Sybil / Provenance Graph Checker
├── Pre-Scoring Risk Gate (GoPlus + RPC simulation)
└── Mode 2 Telegram Alerts (Rich notifications with token stats)

PHASE 2: Autonomous Execution & Position Management
├── Private MEV RPC Bundle Integration (Jito on Solana)
├── Slippage & Gas Priority Fee Optimizer
├── Mode 3 Autonomous Buy Executor
├── Dynamic Position Manager (Multi-tier TP, Trailing Stop, LP Emergency Exit)
└── Telegram Interactive Bot Controls (Configure buy size, pause/resume sniper)

PHASE 3: Multi-Chain Abstraction & Feedback Model
├── Canonical Chain Adapter (Base / EVM support via eth_getLogs)
├── Performance Ledger & Trade Analytics Store
└── Automated Weight Calibrator / Statistical Model for Scoring
```

---

## Configuration Variables (`.env`)

```ini
# --- DATABASE (MONGODB) ---
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=tracking_meme

# --- FOMO INGESTION ---
FOMO_AUTO_REFRESH_ENABLED=true
FOMO_SESSION_PATH=data/fomo_session.json
FOMO_REFRESH_INTERVAL_MINUTES=45
FOMO_3RD_PARTY_API_KEY="" # Optional fallback

# --- CHAIN RPC & INDEXERS ---
SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=xxx
SOLANA_WS_URL=wss://mainnet.helius-rpc.com/?api-key=xxx
BASE_RPC_URL=https://mainnet.base.org

# --- SNIPER ENGINE ---
SNIPER_ENABLED=false # Set true for Mode 3
SNIPER_CHAIN=solana
SNIPER_BUY_AMOUNT_SOL=0.5
SNIPER_MAX_SLIPPAGE_BPS=1500 # 15%
SNIPER_JITO_TIP_LAMPORTS=1000000 # 0.001 SOL
SNIPER_MAX_OPEN_POSITIONS=3

# --- SCORING THRESHOLDS ---
THRESHOLD_RESEARCH=60
THRESHOLD_ALERT=80
THRESHOLD_AUTOSNIPE=90
```

---

## Verification & Test Plan

1. **Resolver Test:** Run historical simulation comparing 5 known Fomo traders with known public wallets to verify $\ge 95\%$ resolution accuracy.
2. **Cluster Detection Unit Test:** Feed mock block swaps from 3 wallets within 30 seconds; assert `conviction >= 1.5` and `is_cluster == True`.
3. **Sybil Resistance Test:** Create a mock funding graph where 4 wallets share funder $F_1$; assert `provenance.is_seeded == True` and signal is dropped.
4. **Paper Trading Dry Run:** Run system against live Solana mainnet stream for 48 hours in Mode 1 & 2; log $\ge 50$ signals without executing live funds; verify false-positive honeypot rate is $0\%$.
