# Plan: Early Token Sniper & Smart Money Radar — Phase 1 (MVP)

**Spec**: `docs/specs/early-token-sniper-radar.md` & `docs/specs/fomo-headless-auth.md`  
**Guidelines**: Strictly adheres to `.claude/CLAUDE.md` and `.claude/rules/`  
**Layer**: Backend Core Services (`bot` service / `radar` modules)  
**Target Chain**: Solana (Raydium + Pump.fun)  
**Database**: MongoDB (`motor` async driver)  
**Testing Standard**: TDD (RED-GREEN-REFACTOR), minimum 80% unit test coverage (`.claude/rules/testing.md`)  
**Commit Format**: Conventional Commits `feat(radar): ...`, `test(radar): ...` (`.claude/rules/git-workflow.md`)  
**Review Gate**: Mandatory Five-Axis Review (Correctness, Readability, Architecture, Security, Performance)

---

## Architecture Overview (Phase 1 MVP)

```
[FOMO_PRIVY_TOKEN / fomo_sessions] ──► [Fomo Client]
                                         │ (Headless worker deferred)
                                         ▼
                                 [Wallet Resolver] (±90s swap correlator)
                                         │
                                         ▼
                               tracked_wallets (MongoDB)
                                         │
                                         ▼
[Solana WS / Helius] ──► [Solana Listener] (Raydium / Pump.fun swaps)
                                 │
                                 ▼
                     [Consensus & Conviction] (2+ wallets within 60s)
                                 │
                                 ▼
                     [Anti-Sybil / Provenance] (Reject seeded crews)
                                 │
                                 ▼
                     [Hard Risk Gate] (Mint/Freeze/Honeypot/LP)
                                 │
                                 ▼
                     [Composite Scorer] (0 - 100 score)
                                 │
                                 ▼
                     token_signals (MongoDB)
                                 │
                          [Score ≥ 80]
                                 │
                                 ▼
                 [Telegram Alert Dispatcher] (Mode 2 Alert)
```

---

## Milestone 1: Database Foundation & MongoDB Integration

- [x] **Task 1.1**: Add MongoDB configuration variables
  - **Files**:
    - `bot/app/config.py`
    - `bot/tests/unit/test_config.py`
    - `.env.example`
  - **Test First (RED)**:
    - Write unit tests in `test_config.py` asserting `Settings()` instantiates with `mongodb_uri` (default: `mongodb://localhost:27017`), `mongodb_db_name` (`tracking_meme`), `solana_rpc_url`, `solana_ws_url`, `fomo_auto_refresh_enabled`.
  - **Implement (GREEN)**:
    - Add fields to `Settings` with `SettingsConfigDict(env_file=".env", extra="ignore")`.
    - Update `.env.example` with documented defaults.
  - **Refactor**:
    - Clean type annotations and validate URI structure.
  - **Acceptance Criteria**:
    - `Settings()` instantiates with sensible defaults and environment overrides. Tests pass.

- [x] **Task 1.2**: Implement Async MongoDB Connection Manager & Index Initializer
  - **Files**:
    - `bot/app/db/mongo.py`
    - `bot/tests/unit/db/test_mongo.py`
  - **Test First (RED)**:
    - Write unit tests mocking `AsyncIOMotorClient`:
      - Singleton database instance creation.
      - Verification that `init_db_indexes(db)` executes `create_index` with expected compound and TTL specs for `tracked_wallets`, `token_signals`, `fomo_sessions`.
      - Graceful error handling and reconnection logging if MongoDB host is unreachable.
  - **Implement (GREEN)**:
    - Implement `bot/app/db/mongo.py` using `motor.motor_asyncio`.
    - Provide `get_db()`, `get_collection(name)`, and `init_db_indexes(db)`.
  - **Refactor**:
    - Ensure clean shutdown on bot exit with client disconnection.
  - **Acceptance Criteria**:
    - Unit tests pass with ≥ 90% coverage for `mongo.py`.

---

## Checkpoint 1: Database Ready
- [x] MongoDB connection and collections initialized.
- [x] Database unit tests pass (`pytest bot/tests/unit/db/test_mongo.py`).

---

## Milestone 2: Fomo Token Management & Provider (Headless Auth Worker Deferred)

- [ ] **Task 2.1**: *(Deferred / Implement Later)* Implement Headless Auth Worker
  - **Status**: **DEFERRED / IMPLEMENT LATER** (Spec: `docs/specs/fomo-headless-auth.md`)
  - **Files**:
    - `bot/app/services/fomo_auth_worker.py`
    - `bot/tests/unit/services/test_fomo_auth_worker.py`
  - **Details**:
    - Automates headless login via Playwright to write fresh tokens to MongoDB `fomo_sessions`.
    - Will be implemented in a subsequent iteration once core radar pipeline is validated.

- [x] **Task 2.2**: Implement `FomoTokenProvider` (Interim: Env Token & MongoDB Cache)
  - **Files**:
    - `bot/app/services/fomo_client.py`
    - `bot/tests/unit/services/test_fomo_token_provider.py`
  - **Test First (RED)**:
    - Write unit tests mocking token resolution:
      - Valid token retrieved from MongoDB `fomo_sessions`.
      - Fallback to `FOMO_PRIVY_TOKEN` when MongoDB has no session.
      - Raising `FomoTokenExpiredError` when token `exp <= time.time() + 60`.
      - Dynamic injection of bearer token into `FomoClient._headers()`.
  - **Implement (GREEN)**:
    - Implement `FomoTokenProvider` with fallback priority: MongoDB → local file → static env.
    - Refactor `FomoClient` to accept `token_provider: FomoTokenProvider | str`.
  - **Refactor**:
    - Preserve backward compatibility with existing tests.
  - **Acceptance Criteria**:
    - Client transparently switches to active token. All existing tests pass. Coverage ≥ 90%.

- [x] **Task 2.3**: Token Health Monitor Job in Telegram Bot
  - **Files**:
    - `bot/app/jobs/fomo_token_refresh.py`
    - `bot/tests/unit/jobs/test_fomo_token_refresh.py`
    - `bot/app/main.py`
  - **Test First (RED)**:
    - Test that job checks token expiration and sends high-priority warning message to `ADMIN_CHAT_ID` if remaining time < 10 minutes.
  - **Implement (GREEN)**:
    - Implement `fomo_token_monitor_job` scheduled every 30 minutes in Telegram `job_queue`.
  - **Refactor**:
    - Prevent spamming alerts if warning was already dispatched recently.
  - **Acceptance Criteria**:
    - Bot sends warning notification before token expires.

- [x] **Task 2.4**: Implement `get_user_following_paginate` in `FomoClient`
  - **Files**:
    - `bot/app/services/fomo_client.py`
    - `bot/tests/unit/services/test_fomo_client.py`
  - **Test First (RED)**:
    - Write unit tests mocking `GET /v2/users/{user_id}/followingPaginate`:
      - Validates parsing of `responseObject.users` with `id`, `address` (Solana), `evmAddress`, `userHandle`, `displayName`, `followers`, `following`, `numTrades`, `totalVolume`, `pnl24h`, and `badge` (`top_100_badge`).
      - Validates `x-supported-chains` header format (`1,56,143,4663,5042,8453,1399811149`).
      - Handles pagination query params (`page`, `limit`).
  - **Implement (GREEN)**:
    - Define `FollowedUser` NamedTuple / Dataclass.
    - Implement `get_user_following_paginate(self, user_id: str, page: int = 1, limit: int = 50) -> list[FollowedUser]`.
  - **Refactor**:
    - Handle null/optional fields (`badge`, `profilePictureLink`, `pnl24h`) gracefully.
  - **Acceptance Criteria**:
    - Returns structured followed user records matching live Fomo API contract. Tests pass with coverage ≥ 90%.

---

## Checkpoint 2: Token Management & Client Resilient
- [x] `FomoTokenProvider` handles static env token and checks `exp` validity.
- [x] Expiry warning notifications active.
- [x] `get_user_following_paginate` tested and operational.
- [x] Downstream resolver can consume Fomo API without breaking.

---

## Milestone 3: Fomo-to-On-Chain Wallet Resolver & Roster Expansion

- [x] **Task 3.1**: Implement `WalletResolver` Service
  - **Files**:
    - `bot/app/services/wallet_resolver.py`
    - `bot/tests/unit/services/test_wallet_resolver.py`
  - **Test First (RED)**:
    - Write unit tests with mock swap fixtures and mock block transaction logs:
      - Given 3 swaps for trader $T$, finds intersecting signer address $W_1$ in $\pm 90$s block windows with confidence 1.0 (3/3).
      - Rejects candidate when confidence $< 0.95$.
      - Correctly upserts resolved wallet into MongoDB `tracked_wallets` with `source="fomo_resolved"`.
  - **Implement (GREEN)**:
    - Implement `WalletResolver.resolve_trader_wallet(trader_handle, fomo_swaps, chain)`.
    - Fetch candidate blocks via RPC and correlate signers.
  - **Refactor**:
    - Optimize parallel block querying with `asyncio.gather` and timeout guards.
  - **Acceptance Criteria**:
    - Resolver correctly unmasks execution wallets with $\ge 95\%$ confidence. Tests pass with coverage $\ge 85\%$.

- [x] **Task 3.2**: Social Graph Expansion & Smart Money Roster Crawler
  - **Files**:
    - `bot/app/services/roster_crawler.py`
    - `bot/tests/unit/services/test_roster_crawler.py`
  - **Test First (RED)**:
    - Write unit tests for `RosterCrawler`:
      - Given top $N$ traders from `/v2/leaderboard`, crawls `/v2/users/{user_id}/followingPaginate`.
      - Aggregates unique users and calculates `peer_endorsement_count` (how many top traders follow them).
      - Upserts discovered Solana (`address`) and EVM (`evmAddress`) wallets into MongoDB `tracked_wallets` with:
        - `source="fomo_following_expansion"`
        - `fomo_handle`
        - `peer_endorsement_count`
        - Base wallet score computed from `pnl24h`, `totalVolume`, `badge`, and `peer_endorsement_count`.
      - Rate-limiting guard prevents API flooding (sleep between user paginate requests).
  - **Implement (GREEN)**:
    - Implement `RosterCrawler.crawl_top_traders_network(top_n=20)`.
    - Save/update records in MongoDB collection `tracked_wallets`.
  - **Refactor**:
    - Deduplicate by `address` and merge endorsement lists.
  - **Acceptance Criteria**:
    - Expands tracked smart wallet database to 200–500 high-conviction wallets followed by leaderboard legends. Tests pass.

---

## Checkpoint 3: Wallet Resolver & Roster Expansion Functional
- [x] Resolver successfully identifies execution wallets from swap history.
- [x] Top trader following networks crawled and indexed in MongoDB `tracked_wallets`.
- [x] Tracked smart wallet pool expanded with peer endorsement metrics.

---

## Milestone 4: Solana On-Chain Realtime Ingestion

- [x] **Task 4.1**: Implement Solana WebSocket Event Listener
  - **Files**:
    - `bot/app/services/chain/solana_listener.py`
    - `bot/tests/unit/services/test_solana_listener.py`
  - **Test First (RED)**:
    - Write unit tests feeding sample Raydium Pool V4 and Pump.fun raw log strings:
      - Validates parsing of `mint`, `user_wallet`, `is_buy`, `amount_usd`, `timestamp`, `signature`.
      - Verifies event is matched against in-memory `tracked_wallets` cache.
      - Verifies exponential backoff reconnection on socket close.
  - **Implement (GREEN)**:
    - Implement `SolanaEventListener` with async WebSocket loop using `websockets` or `aiohttp`.
    - Connect to `SOLANA_WS_URL` and subscribe via `logsSubscribe`.
    - Forward matched swap events to `ConsensusEngine`.
  - **Refactor**:
    - Use efficient parsing with pre-compiled regex for instruction log markers.
  - **Acceptance Criteria**:
    - Parsed swap models accurately extracted from live log formats. Tests pass with coverage $\ge 85\%$.

---

## Checkpoint 4: Chain Listener Operational
- [x] WebSocket listens to Solana DEX swaps in real time.
- [x] Filter accurately flags swaps originating from tracked smart wallets.

---

## Milestone 5: Smart Money Consensus, Earlyness & Anti-Sybil

- [x] **Task 5.1**: Implement `ConsensusEngine` & Earlyness Decay
  - **Files**:
    - `bot/app/services/consensus_engine.py`
    - `bot/tests/unit/services/test_consensus_engine.py`
  - **Test First (RED)**:
    - Write unit tests:
      - Single wallet buy does NOT trigger consensus.
      - 2 wallets with scores 90 and 80 within 60s trigger consensus with $\text{Conviction} = 0.9^2 + 0.8^2 = 1.45$.
      - Earlyness decay multiplier correctly calculated ($1.0\times$ for age $\le 60$s, $0.5\times$ for 30m, $0.1\times$ for 10h).
      - Heat correctly computed as $\text{Conviction} \times \text{Earlyness}$.
  - **Implement (GREEN)**:
    - Implement `ConsensusEngine` with sliding window cache (`defaultdict(list)` with timestamp expiry).
  - **Refactor**:
    - Add periodic cleanup for stale token windows.
  - **Acceptance Criteria**:
    - Quadratic conviction and earlyness decay match spec exactly. Tests pass.

- [x] **Task 5.2**: Implement `ProvenanceChecker` (Anti-Sybil / Crew Filter)
  - **Files**:
    - `bot/app/services/provenance_checker.py`
    - `bot/tests/unit/services/test_provenance_checker.py`
  - **Test First (RED)**:
    - Write unit tests:
      - Cluster with 4 wallets where 2 share the same funder ($50\% \ge 40\%$) triggers `is_sybil=True` and drops signal.
      - Cluster with 3 independent wallets passes with `is_sybil=False`.
  - **Implement (GREEN)**:
    - Implement `ProvenanceChecker.check_cluster_provenance(wallets)`.
    - Query RPC for initial funding transaction and parse sender address.
  - **Refactor**:
    - Cache checked wallet funding parents in MongoDB to avoid repeat RPC queries.
  - **Acceptance Criteria**:
    - Sybil seeded crews blocked from advancing to risk gate. Coverage $\ge 85\%$.

---

## Checkpoint 5: Signal Consensus & Anti-Sybil Validated
- [x] Consensus clusters accurately detected.
- [x] Seeded sybil crews successfully filtered out.

---

## Milestone 6: Hard Risk Gate & Composite Signal Scorer

- [x] **Task 6.1**: Implement `RiskGate`
  - **Files**:
    - `bot/app/services/risk_gate.py`
    - `bot/tests/unit/services/test_risk_gate.py`
  - **Test First (RED)**:
    - Write unit tests:
      - Token with active mint authority fails (`risk_passed=False`).
      - Token with active freeze authority fails.
      - Token with $< 80\%$ LP burned/locked fails.
      - Token with simulated sell tax $> 15\%$ fails.
      - Fully clean token passes (`risk_passed=True`).
  - **Implement (GREEN)**:
    - Implement `RiskGate.audit_token(token_address, chain)` integrating RPC state checks and GoPlus / DexScreener APIs.
  - **Refactor**:
    - Fast fail: return immediately on first failing security parameter.
  - **Acceptance Criteria**:
    - All honeypot/scam tokens rejected. Tests pass with coverage $\ge 90\%$.

- [x] **Task 6.2**: Implement `SignalScorer`
  - **Files**:
    - `bot/app/services/signal_scorer.py`
    - `bot/tests/unit/services/test_signal_scorer.py`
  - **Test First (RED)**:
    - Write unit tests:
      - Verifies weighted formula: SmartMoney(30%) + Momentum(25%) + Safety(20%) + LP(15%) + Social(10%).
      - Asserts score is bounded between $0$ and $100$.
      - Verifies signal document inserted into MongoDB `token_signals` collection with correct index fields.
  - **Implement (GREEN)**:
    - Implement `SignalScorer.compute_score(token_snapshot)`.
    - Save scored document to MongoDB.
  - **Refactor**:
    - Clean type hints and structured dataclasses.
  - **Acceptance Criteria**:
    - Composite scores match spec. Document saved in MongoDB. Coverage $\ge 90\%$.

---

## Checkpoint 6: Risk Filter & Scoring Verified
- [x] Risky/honeypot tokens hard-rejected.
- [x] Qualified tokens scored accurately and stored in MongoDB `token_signals`.

---

## Milestone 7: Mode 2 Telegram Alert Integration

- [x] **Task 7.1**: Implement `RadarAlertFormatter`
  - **Files**:
    - `bot/app/handlers/radar_alert.py`
    - `bot/tests/unit/handlers/test_radar_alert.py`
  - **Test First (RED)**:
    - Write unit tests asserting generated HTML/Markdown matches UI template:
      - Valid token name, symbol, CA monospace, age badge, MC, liquidity.
      - Smart wallets cluster details.
      - Inline keyboard buttons with valid links and callback data.
  - **Implement (GREEN)**:
    - Implement `RadarAlertFormatter.format_alert(signal_doc)` returning text and `InlineKeyboardMarkup`.
  - **Refactor**:
    - Escape special Markdown characters to prevent Telegram parse errors.
  - **Acceptance Criteria**:
    - Alert renders cleanly with zero parse errors.

- [x] **Task 7.2**: Connect Signal Pipeline to Telegram Dispatch Queue
  - **Files**:
    - `bot/app/jobs/radar_alert_dispatcher.py`
    - `bot/tests/unit/jobs/test_radar_alert_dispatcher.py`
    - `bot/app/main.py`
  - **Test First (RED)**:
    - Write unit tests verifying dispatcher broadcasts alerts to subscribed chat IDs when score $\ge 80$ and marks document `dispatched=True`.
  - **Implement (GREEN)**:
    - Implement `radar_alert_dispatcher_job` polling new signals from MongoDB.
    - Register job in `main.py` `job_queue`.
  - **Refactor**:
    - Batch send with rate-limit throttling to prevent Telegram 429 limits.
  - **Acceptance Criteria**:
    - Real-time alert dispatched within $< 3\text{s}$ of cluster confirmation.

---

## Milestone 8: Final Checkpoint, E2E Simulation & Code Review

- [x] **Task 8.1**: End-to-End Simulation Test
  - **Files**:
    - `bot/tests/integration/test_radar_e2e.py`
  - **Details**:
    1. Seed MongoDB `tracked_wallets` with 2 mock smart wallets.
    2. Stream 2 mock Solana swap events for Token $X$ within 20s.
    3. Assert `ConsensusEngine` triggers cluster detection.
    4. Assert `RiskGate` checks pass.
    5. Assert `SignalScorer` outputs score $\ge 80$.
    6. Assert `token_signals` document inserted in MongoDB.
    7. Assert Telegram alert is queued with matching token address.

- [x] **Task 8.2**: Mandatory Five-Axis Review (`.claude/rules/code-style.md`, `clean-code.md`, `security.md`)
  - **Axes Verified**:
    1. **Correctness**: All unit & integration tests pass with $\ge 85\%$ coverage. No regressions.
    2. **Readability**: Type annotations, docstrings, clean function boundaries.
    3. **Architecture**: Clean layered architecture (DB → Services → Jobs → Handlers).
    4. **Security**: No secrets or private keys logged or committed; inputs validated.
    5. **Performance**: Async non-blocking I/O (`motor`, `websockets`, `httpx`). Fast memory lookups.


