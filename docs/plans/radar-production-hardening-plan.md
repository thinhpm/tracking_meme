# Implementation Plan: Radar Production Hardening & Anti-Exploit

This plan translates [`docs/specs/radar-production-hardening.md`](file:///Users/thinhpm/Documents/projects/AI/tracking_meme/docs/specs/radar-production-hardening.md) into concrete development tasks, test coverage, and rollout verification.

---

## Proposed Changes

### 1. Consensus Engine: Continuous Earlyness & Undated Fallback
- File: [`bot/app/services/consensus_engine.py`](file:///Users/thinhpm/Documents/projects/AI/tracking_meme/bot/app/services/consensus_engine.py)
- Replace discrete threshold checks with continuous formula:
  $$\text{Earliness}(\Delta t) = \frac{1.0}{1.0 + \frac{\max(\Delta t, 0)}{3600}}$$
- Set default for unknown launch timestamp to $0.50$ (1h equivalent), never $1.0$.
- Update `calculate_heat` to multiply continuous earliness by quadratic conviction.

### 2. Provenance Checker: Median-Scaled Dust & Seeding Waves
- File: [`bot/app/services/provenance_checker.py`](file:///Users/thinhpm/Documents/projects/AI/tracking_meme/bot/app/services/provenance_checker.py)
- Add `is_dust_buy(usd_value, median_buy_usd)`:
  $$\text{threshold} = \max(\$10.0, 0.05 \times \text{median\_buy\_usd})$$
- Add wave detection: If $\ge 3$ smart wallets receive dust or direct fills within 24h $\rightarrow$ Flag token as `SEEDED` and reject.
- Separate `kind = 'direct'` fills (caller $\ne$ wallet) from organic swaps.

### 3. Risk Gate: Pool Silence Honeypot Check
- File: [`bot/app/services/risk_gate.py`](file:///Users/thinhpm/Documents/projects/AI/tracking_meme/bot/app/services/risk_gate.py)
- Add `check_pool_silence(buys_24h, sells_24h, pool_age_seconds)`:
  - If $\text{buys} \ge 8$ and $\text{sells} == 0$ after $T_{\text{wait}}(\text{buys})$: Fail with reason `HONEYPOT_POOL_SILENCE`.
  - Override if `cohort_sold == True`.

### 4. Signal Scorer: Strict Liquidity Floor & Dynamic Momentum
- File: [`bot/app/services/signal_scorer.py`](file:///Users/thinhpm/Documents/projects/AI/tracking_meme/bot/app/services/signal_scorer.py)
- Hard requirement: `liquidity_depth >= 0.20` and pool liquidity $\ge \$10,000$ for `A_GRADE_SNIPER`.
- Tokens failing liquidity floor get capped at Score 65 (`status: research`).
- Refine `volume_acceleration` calculation using buy ratio and 1h price change.

### 5. Crew & Anti-Sybil Clustering Service
- File: `bot/app/services/crew_detector.py`
- Group buyers within $\le 45\text{s}$ window and $\ge 3$ shared historical tokens into a single crew.
- When computing consensus, take $\max(\text{score})$ per crew, preventing swarm sybil attacks.

### 6. Pipeline Integration & Live Verification Script
- File: [`bot/scripts/crawl_real_fomo.py`](file:///Users/thinhpm/Documents/projects/AI/tracking_meme/bot/scripts/crawl_real_fomo.py)
- Integrate all hardened checks into the real-data live crawling script.
- Verify that bad pools (e.g. $2k liquidity, -98% crash) are downgraded to Research/Watchlist, while healthy pools pass to `A_GRADE_SNIPER`.

---

## Verification Plan

### Automated Tests
1. **Unit Tests:**
   - `bot/tests/unit/services/test_consensus_continuous_earliness.py`: Validate formula outputs for 0s, 60s, 1h, 10h, and None (undated).
   - `bot/tests/unit/services/test_provenance_dust.py`: Validate dust identification against wallet median buy.
   - `bot/tests/unit/services/test_risk_gate_pool_silence.py`: Test dynamic $T_{\text{wait}}$ formula and honeypot detection.
   - `bot/tests/unit/services/test_crew_clustering.py`: Validate crew grouping and single-vote consensus collapse.
2. **Regression Test:**
   - Run complete test suite: `.venv/bin/pytest bot/tests/` $\rightarrow$ Ensure 100% pass rate.

### Live End-to-End Verification
- Run `.venv/bin/python bot/scripts/crawl_real_fomo.py` with real on-chain Solana tokens and verify clean alerts, zero emojis, and accurate risk grading.
