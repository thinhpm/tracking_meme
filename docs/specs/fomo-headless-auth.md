# Feature: Fomo Headless Authentication & Token Auto-Refresh

## Objective

Automate the acquisition and periodic renewal of Privy JWT authentication tokens for `prod-api.fomo.family`. Because Fomo's web session tokens expire every 60 minutes (`exp`), this feature introduces an autonomous headless browser daemon/worker (Playwright) that authenticates with Fomo, extracts fresh Privy session tokens, and seamlessly supplies them to `FomoClient` without requiring manual developer intervention or service downtime.

---

## Target Users & Systems

- **Telegram Bot Daemon:** Runs 24/7 background jobs (`fomo_watching_alert`, `fomo_leaderboard_alert`) without failing due to `FomoTokenExpiredError` or HTTP 401.
- **System Operators:** Eliminates the need to manually extract cookies/bearer tokens from DevTools every hour.
- **Future On-Chain & Sniper Services:** Provides a reliable upstream metadata source for trader roster and following list.

---

## Layer

- [x] Backend / Bot service (`bot` service)
- [x] Headless Automation Worker (Playwright / Node or Python)
- [ ] API service (`api`)
- [ ] Frontend UI

---

## Core Features & Acceptance Criteria

| # | Feature | Acceptance Criteria |
|---|---------|---------------------|
| 1 | **Autonomous Headless Login Worker** | A lightweight Playwright worker navigates to `https://fomo.family`, connects via wallet signature or restores a persistent browser profile session, and captures the fresh Privy JWT bearer token. |
| 2 | **Dynamic Token Provider Interface** | `FomoClient` transitions from a static `token: str` in `__init__` to a dynamic `TokenProvider` (or callable `get_token()`) that checks token validity (`exp`) and retrieves the latest active token automatically. |
| 3 | **Token Storage & Cache Strategy** | Persist extracted tokens with metadata (`access_token`, `expires_at`, `refreshed_at`) into MongoDB collection `fomo_sessions` (with atomic upsert) and shared local cache (`data/fomo_session.json`, 0600). |
| 4 | **Proactive Scheduled Renewal** | A scheduled job triggers renewal at ~45-50 minutes (prior to the 60-minute expiration mark) so that inflight HTTP requests never encounter an expired token. |
| 5 | **On-Demand Expiry Fallback** | If `FomoClient` receives a 401 or detects an expired token during a call, it can trigger an immediate on-demand refresh request before failing. |
| 6 | **Telegram Notification on Renewal Failure** | If the headless login worker fails 3 consecutive times, an urgent administrative alert is dispatched to `ADMIN_CHAT_ID` via Telegram. |
| 7 | **Backward Compatibility** | If headless login is disabled or unconfigured (`FOMO_AUTO_REFRESH_ENABLED=false`), `FomoClient` gracefully falls back to a static `FOMO_PRIVY_TOKEN` from `.env`. |

---

## Out of Scope

- Reverse-engineering Privy's proprietary backend cryptography/HMAC keys.
- Real-time high-frequency transaction scraping via Fomo web (real-time transactions will transition to direct on-chain RPC).
- Commercial 3rd-party `fomoapi` integration (handled as an independent fallback provider).
- Full browser GUI rendering in production (the worker runs entirely `--headless`).

---

## Technical Architecture

```
                    ┌────────────────────────────────────────┐
                    │       Headless Auth Worker             │
                    │   (Playwright Python / Chromium)       │
                    │                                        │
                    │  1. Launch headless browser            │
                    │  2. Load user session / connect wallet │
                    │  3. Extract `privy:token` from storage │
                    └───────────────────┬────────────────────┘
                                        │ (Every 45-50 min)
                                        ▼
                    ┌────────────────────────────────────────┐
                    │       Token Store / Shared Cache       │
                    │      (data/fomo_session.json)          │
                    │                                        │
                    │  - access_token: "eyJhbGciOi..."       │
                    │  - expires_at: 1790652400              │
                    │  - updated_at: 1790649400              │
                    └───────────────────┬────────────────────┘
                                        │ Read on demand
                                        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                              Bot Service                               │
 │                                                                        │
 │   ┌──────────────────────┐          ┌──────────────────────────────┐   │
 │   │  FomoTokenProvider   │ ───────► │         FomoClient           │   │
 │   └──────────────────────┘          │   - get_leaderboard()        │   │
 │                                     │   - get_following()          │   │
 │                                     │   - get_user_activity()      │   │
 │                                     └──────────────┬───────────────┘   │
 │                                                    │                   │
 └────────────────────────────────────────────────────┼───────────────────┘
                                                      │ HTTP Bearer
                                                      ▼
                                      ┌───────────────────────────────┐
                                      │   https://prod-api.fomo.family│
                                      └───────────────────────────────┘
```

---

## Detailed Component Design

### 1. Headless Worker (`bot/app/services/fomo_auth_worker.py`)

#### Authentication Strategies
The worker will support two operational modes:

1. **Mode A: Persistent Browser Profile / Cookies (Recommended for Initial Release)**
   - Maintain a persistent Chromium `user_data_dir` located at `.fomo_browser_profile/`.
   - On the first manual run (`python -m app.services.fomo_auth_worker --manual-login`), the operator logs in once in headful mode (wallet connect / OTP).
   - Subsequent headless runs reuse the persisted cookies, IndexedDB, and LocalStorage state. When visiting `https://fomo.family`, Privy automatically refreshes the session without user prompts.

2. **Mode B: Automated Burner Wallet Signature (Fully Autonomous)**
   - Inject a mock or programmatic EIP-1193 / Solana wallet provider into the page context using a dedicated burner private key (`FOMO_BURNER_PRIVATE_KEY`).
   - Auto-confirm the Privy connection dialog and message signing requests.

#### Token Extraction Logic
Once the page is loaded and session initialized:
```javascript
// Extract token from LocalStorage or Privy SDK context
const privyToken = localStorage.getItem('privy:token');
const privyRefreshToken = localStorage.getItem('privy:refresh_token');
```
The worker extracts the token, validates the JWT `exp` payload, writes the token record atomically to disk, and exits cleanly.

---

### 2. Token Cache Schema (MongoDB `fomo_sessions` & `data/fomo_session.json`)

Stored in MongoDB collection `fomo_sessions` (query by `_id: "current"` with upsert) and written to `data/fomo_session.json`:

```json
{
  "_id": "current",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_at": ISODate("2026-09-29T11:00:00Z"),
  "refreshed_at": ISODate("2026-09-29T10:00:00Z"),
  "source": "headless_worker",
  "status": "valid"
}
```

---

### 3. Dynamic Token Provider in `FomoClient`

Refactor [bot/app/services/fomo_client.py](file:///Users/thinhpm/Documents/projects/AI/tracking_meme/bot/app/services/fomo_client.py):

```python
class FomoTokenProvider:
    """Reads and caches the active Privy token from shared storage or fallback env."""

    def __init__(self, session_path: str, fallback_token: str = ""):
        self._session_path = session_path
        self._fallback_token = fallback_token

    def get_token(self) -> str:
        """Returns valid token from cache file, or falls back to static env token."""
        # 1. Check local session file
        # 2. Verify time.time() < exp - 60s
        # 3. Fall back to self._fallback_token if valid
        # 4. Raise FomoTokenExpiredError if no valid token exists


class FomoClient:
    def __init__(self, token_provider: FomoTokenProvider | str) -> None:
        if isinstance(token_provider, str):
            self._token_provider = StaticTokenProvider(token_provider)
        else:
            self._token_provider = token_provider

    def _headers(self) -> dict[str, str]:
        token = self._token_provider.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Supported-Chains": "ethereum,bsc,solana,base,arbitrum",
            "App-Language": "en",
            "User-Agent": _USER_AGENT,
            "Origin": "https://fomo.family",
            "Referer": "https://fomo.family/",
        }
```

---

### 4. Background Job Scheduling

Register a scheduled job inside `bot/app/main.py`:

```python
# Run headless refresh every 45 minutes
job_queue.run_repeating(
    fomo_token_refresh_job,
    interval=45 * 60,
    first=10,  # 10s after startup
    name="fomo_token_refresh",
)
```

If `fomo_token_refresh_job` encounters an exception:
1. Log warning and retry once after 2 minutes.
2. If retry fails, continue using cached token until `exp`.
3. When token is within 5 minutes of expiration and refresh still fails, send Telegram alert to `ADMIN_CHAT_ID`.

---

## Configuration Variables (`bot/app/config.py`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `FOMO_PRIVY_TOKEN` | `str` | `""` | Fallback static bearer token. |
| `FOMO_AUTO_REFRESH_ENABLED` | `bool` | `true` | Enable/disable headless Playwright worker. |
| `FOMO_SESSION_PATH` | `str` | `data/fomo_session.json` | Path to shared token JSON file. |
| `FOMO_BROWSER_PROFILE_DIR` | `str` | `.fomo_browser_profile` | Directory for persistent browser session. |
| `FOMO_REFRESH_INTERVAL_MINUTES` | `int` | `45` | Interval in minutes between scheduled headless runs. |
| `FOMO_AUTH_HEADLESS` | `bool` | `true` | Run browser in headless mode (false for manual bootstrap). |

---

## Security Considerations

1. **File Permissions:** `data/fomo_session.json` and `.fomo_browser_profile/` must be included in `.gitignore` and chmoded to `0600`.
2. **Token Sanitization:** JWT tokens must be masked in application logs (`eyJ...****`).
3. **Burner Wallet Isolation:** If Mode B (wallet signature) is used, only use a fresh burner wallet with $0 balance strictly dedicated to Privy message signing.

---

## Test & Verification Plan

1. **Unit Tests (`tests/test_fomo_token_provider.py`):**
   - Verify token extraction and `exp` parsing.
   - Verify fallback to `FOMO_PRIVY_TOKEN` when session file is absent or invalid.
   - Verify `FomoTokenExpiredError` when all tokens are expired.
2. **Integration Test (`tests/test_fomo_auth_worker.py`):**
   - Mock Playwright page evaluate response and verify `data/fomo_session.json` is written atomically.
   - Verify `FomoClient.get_leaderboard()` successfully picks up refreshed token without restarting client instance.
3. **Manual CLI Bootstrap Test:**
   - Execute `python -m app.services.fomo_auth_worker --manual-login` to initialize browser profile.
   - Execute `python -m app.services.fomo_auth_worker --headless` and assert valid token in `data/fomo_session.json`.
