# Specification: Radar Production Hardening & Anti-Exploit Architecture

## 1. Overview & Context

This specification documents the production-hardening upgrades for the **Early Token Sniper & Smart Money Radar Platform** (`tracking_meme`), incorporating empirical battle-tested mechanisms from [`fomo-robinhood-radar`](file:///Users/thinhpm/Documents/projects/AI/fomo-robinhood-radar).

### 1.1 Problems Solved
1. **Low-Liquidity / Rug Qualification:** Early prototypes allowed micro-cap pools with depleted liquidity (e.g. $2,300 liquidity, -98% price dump) to score $\ge 80$ and trigger `A_GRADE_SNIPER` alerts.
2. **Router-Direct Seeding Attacks:** Malicious token deployers inject micro-swaps ($0.50–$30) directly through swap routers with smart money wallets as recipients. Naive trackers attribute these to smart money "buying", triggering false consensus alerts.
3. **Copy-Bot / Sybil Swarms:** A single trader or bot running 6–10 linked sub-wallets creates artificial consensus volume if counted individually.
4. **Honeypot "Pool Silence":** Many honeypots pass basic static contract checks but block sales on-chain. When a pool has tens of buys and zero sells over 30 minutes, buyers are trapped.
5. **Discrete Step Earlyness:** Step-wise earlyness penalties (e.g. $<5\text{m}, <15\text{m}$) cause erratic score cliffs and improperly rank tokens with missing launch timestamps above real early trades.

---

## 2. Hardened Architecture & Subsystems

```
                                  LIVE ON-CHAIN INGEST
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │ 1. Noise & Hyperactive Filter (noise.py)  │
                     │    - Quarantines DEX Aggregators / MEVs   │
                     │    - Threshold: >50 unique tokens / hour  │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │ 2. Provenance & Dust Gate (provenance.py) │
                     │    - Rejects router-direct recipient txs  │
                     │    - Dust: < max($10, 5% of median buy)   │
                     │    - Wave Blacklist: ≥3 wallets touched   │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │ 3. Crew & Sybil De-duplication (crews.py) │
                     │    - Detects temporal clusters (≤45s)     │
                     │    - ≥3 shared tokens → Collapses to 1 vote│
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │ 4. Smooth Decay Consensus & Heat Engine   │
                     │    - Quadratic Conviction: Σ(score/100)²  │
                     │    - Continuous Earlyness: 1 / (1 + Δt/3600)│
                     │    - Undated tokens fallback to 1h (0.50) │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │ 5. Pool Silence & Sell Gate (safety.py)   │
                     │    - 0 sells after dynamic wait → HONEYPOT│
                     │    - Bypass: Cohort sold verified (> $0)  │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │ 6. Signal Scorer & Liquidity Depth Floor  │
                     │    - Liquidity Depth ≥ $10,000 for Sniper │
                     │    - Price change & Buy/Sell ratio scoring │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                                 QUALIFIED RADAR ALERT
```

---

## 3. Detailed Component Specifications

### 3.1 Smooth Continuous Earlyness & Heat Function

#### Formula
Instead of discrete buckets, earlyness decays continuously based on elapsed seconds $\Delta t = t_{\text{entry}} - t_{\text{launch}}$:

$$\text{Earliness}(\Delta t) = \frac{1.0}{1.0 + \frac{\max(\Delta t, 0)}{3600}}$$

$$\text{Heat}(T) = \sum_{w \in \text{buyers}} \left( \frac{\text{Score}(w)}{100} \right)^2 \times \text{Earliness}(\Delta t_w)$$

#### Critical Fallback Rule for Undated Tokens
When pool creation timestamp $t_{\text{launch}}$ is missing (`None`), assign:
$$\text{Earliness}_{\text{undated}} = 0.50 \quad (\text{equivalent to exactly 1 hour old})$$
*Rule:* **Never** assign $1.0$ to undated tokens; otherwise unindexed new tokens artificially leapfrog genuine sub-minute snipes.

---

### 3.2 Anti-Dust & Seeding Attack Provenance Filter

#### A. Direct vs Ingested Trade Distinction
- If transaction receipt indicates the caller interacted directly with the router specifying a tracked wallet as `recipient` without origin signature from the wallet:
  - Mark `kind = 'direct'`
  - **Exclude completely** from consensus calculations.

#### B. Dynamic Dust Threshold
For each tracked wallet $w$, compute historical median buy size $\text{median\_buy\_usd}(w)$ over the last 30 days:
$$\text{DustThreshold}(w) = \max\left(\$10.0, \, 0.05 \times \text{median\_buy\_usd}(w)\right)$$
Any buy with $\text{usd\_value} < \text{DustThreshold}(w)$ is tagged as `dust` and excluded from quadratic conviction.

#### C. Seeding Wave Blacklist
If within any 24-hour window, $\ge 3$ distinct tracked wallets receive `dust` or `direct` fills for the same token $T$:
- Flag token as `is_seeded = True`
- Permanently purge and block token $T$ from all feeds and alerts.

---

### 3.3 Pool Silence & Honeypot Sell Verification

A token with 100% buy transactions and 0 sells is almost always a honeypot.

#### Dynamic Silence Wait Time
Let $B$ be the number of pool buy transactions in the last 24 hours:
$$T_{\text{wait}}(B) = \text{int}\left( \max\left(600, \, \min\left(1800, \, 1800 \times \frac{8}{B}\right)\right) \right) \quad (\text{seconds})$$

- For $B = 8$ buys: $T_{\text{wait}} = 1800\text{s}$ (30 minutes).
- For $B = 80$ buys: $T_{\text{wait}} = 600\text{s}$ (10 minutes).
- For $B \ge 100$ buys with 0 sells: flags instantly after 10 minutes.

#### Verification Verdict
1. If $\text{sells} > 0$: Status is `PASS`.
2. If $\text{buys} \ge 8$, $\text{sells} == 0$, and $\text{pool\_age} \ge T_{\text{wait}}(B)$: Mark `sellable = False` with reason `SILENCE: B buys and 0 sells after age`. **Hard Reject**.
3. **Cohort Sold Override:** If the database contains at least 1 verified sell transaction with $\text{usd\_value} > 0$ from any tracked wallet on token $T$, the token is confirmed sellable.

---

### 3.4 Crew & Copy-Bot Clustering

#### Detection Criteria
Two tracked wallets $W_a$ and $W_b$ belong to the same **Crew** if:
1. They bought the same token within $\Delta t \le 45\text{ seconds}$ of each other.
2. This co-entry pattern has occurred across $\ge 3$ distinct tokens over the last 30 days.

#### Consensus Aggregation
When calculating consensus for a token $T$:
- Group buyer wallets by their assigned `crew_id`.
- For each crew $C = \{W_1, W_2, \dots, W_m\}$, collapse the group into a **single vote**:
  $$\text{CrewScore}(C) = \max_{w \in C} \text{Score}(w)$$
  $$\text{Conviction Contribution}(C) = \left( \frac{\text{CrewScore}(C)}{100} \right)^2$$
- Prevents 1 actor with 10 copy-wallets from fabricating a 10-wallet swarm.

---

### 3.5 Hyperactive Noise & Router Quarantine

#### Rule
During any 1-hour window:
- If a wallet interacts with $> 50$ distinct token mints, or executes $> 200$ swap transactions:
  - Flag wallet as `is_quarantined = True` (`reason = 'hyperactive_mev_or_router'`).
  - Automatically drop wallet from `tracked_wallets`.
  - Delete its historical fills from consensus calculation.

---

### 3.6 Whale Distribution Gate

#### Rule
Track the 7-day rolling flow for each smart wallet:
$$\text{IsDistributing}(w) = (\text{sold\_usd} \ge \$50,000) \quad \text{AND} \quad (\text{sold\_usd} \ge 5.0 \times \max(\text{bought\_usd}, 1.0))$$
- If `True`: Wallet state changes to `status = 'watch'`.
- Any purchases by this wallet are treated as low-confidence probe fills and do not count toward high-conviction cluster formation.

---

### 3.7 Hard Liquidity Floor & Dynamic Momentum Qualification

#### Hard Liquidity Depth Floor
To qualify as `A_GRADE_SNIPER` (Score $\ge 80$):
- **Real Liquidity USD:** Must be $\ge \$10,000$ (or `liquidity_depth >= 0.20` relative to market cap).
- If liquidity $< \$10,000$: Downgrade score to $\le 65$ (`WATCHLIST`, `Mode 1: Research`).

#### Dynamic Momentum Formula
Using live DexScreener/GeckoTerminal metrics:
$$\text{BuyRatio} = \frac{\text{buys}_{h1}}{\max(\text{buys}_{h1} + \text{sells}_{h1}, 1)}$$
$$\text{PriceFactor} = \max\left(0.0, \, \min\left(1.0, \, 0.5 + \frac{\text{priceChange}_{h1}}{200.0}\right)\right)$$
$$\text{VolumeAcceleration} = 0.6 \times \text{BuyRatio} + 0.4 \times \text{PriceFactor}$$

---

## 4. Database Schema Migrations (MongoDB)

### 4.1 Collection: `tracked_wallets`
```json
{
  "_id": "ObjectId",
  "address": "String (indexed, unique)",
  "chain": "solana",
  "fomo_handle": "String",
  "score": 85,
  "median_buy_usd": 1250.0,
  "flow_7d": {
    "bought_usd": 12000.0,
    "sold_usd": 4500.0,
    "is_distributing": false
  },
  "crew_id": "crew_sol_98a7",
  "is_quarantined": false,
  "updated_at": "ISODate"
}
```

### 4.2 Collection: `signals`
```json
{
  "_id": "ObjectId",
  "token_mint": "String (indexed)",
  "chain": "solana",
  "score": 82,
  "qualification": "A_GRADE_SNIPER",
  "heat": 2.45,
  "conviction": 2.68,
  "earliness": 0.91,
  "distinct_crews": 2,
  "buyers_count": 3,
  "dust_filtered_count": 1,
  "pool_silence": {
    "buys_24h": 142,
    "sells_24h": 68,
    "verdict": "PASS"
  },
  "created_at": "ISODate"
}
```

---

## 5. Implementation Roadmap & Verification

1. **Phase 1: Formula Upgrades**
   - Update `bot/app/services/consensus_engine.py`: Continuous earlyness function and undated token $0.50$ penalty.
   - Update `bot/app/services/signal_scorer.py`: Enforce $\$10,000$ liquidity floor and dynamic momentum.
2. **Phase 2: Provenance & Safety Upgrades**
   - Update `bot/app/services/provenance_checker.py`: Median-scaled dust filter and seeding wave detection.
   - Update `bot/app/services/risk_gate.py`: Add `pool_silence` check with buy/sell counts and age limits.
3. **Phase 3: Crew & Noise Filter**
   - Implement `bot/app/services/crew_detector.py`: Clustering pairs into crews.
   - Implement `bot/app/services/noise_quarantine.py`: Hyperactive wallet quarantine.
4. **Phase 4: Full Pipeline Integration & Alert Verification**
   - Update `bot/scripts/crawl_real_fomo.py` to use all hardened services.
   - Run live test and verify zero low-liquidity/honeypot false positives.
