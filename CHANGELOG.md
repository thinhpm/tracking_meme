# Changelog

All notable changes to this project will be documented in this file.

Format: [Semantic Versioning](https://semver.org/). Dates in `YYYY-MM-DD`.

---

## [Unreleased]

---

## [0.6.0] — 2026-09-28

### Added — LLM Gemini Service Integration

- **`GeminiClient`** (`api/app/services/gemini_client.py`)
  - Client bất đồng bộ kết nối tới centralized LLM Gateway service (`POST {url}/prompt`)
  - Tự động lọc bỏ thẻ reasoning `<think>...</think>`, markdown code fences (` ```json `), và bóc tách JSON object
  - Tự động retry với exponential backoff khi gặp lỗi 502 / network
  - Hỗ trợ tuỳ biến `provider`, `model`, `effort`, `timeout`
- **Multi-provider `AnalysisService`** (`api/app/services/analysis_service.py`)
  - Tự động định tuyến: sử dụng Claude Haiku nếu có `ANTHROPIC_API_KEY`; tự động chuyển sang `GeminiClient` nếu để trống `ANTHROPIC_API_KEY`
  - Dự phòng an toàn: tự động fallback về `heuristic_analysis` nếu LLM gặp sự cố
- **Config & Dependency Injection** (`api/app/config.py`, `api/app/routes/token.py`)
  - Chuyển `anthropic_api_key` thành optional (mặc định `""`)
  - Thêm cấu hình `gemini_service_url`, `gemini_service_provider`, `gemini_service_model`
  - Route token search tự động inject `GeminiClient` khi không có Anthropic key

### Added — Production Deployment (Raspberry Pi)

- **Dedicated Production Services** (`docker-compose.yml`)
  - Bổ sung `api-prod` và `bot-prod` dành riêng cho môi trường deploy Pi / Server
  - Giao tiếp nội bộ không cần map port API ra ngoài host
  - `extra_hosts: ["host.docker.internal:host-gateway"]` kết nối tới Gemini Gateway service trên host Pi
  - DNS ổn định (`8.8.8.8`, `1.1.1.1`) và log rotation (`10m`, max 3 files) chống đầy thẻ nhớ SD

### Fixed — Telegram Bot Connection Pool & Timeouts

- **`HTTPXRequest` Connection Pooling** (`bot/app/main.py`)
  - Tách riêng `request` và `get_updates_request` tránh xung đột giữa long-polling và gửi tin nhắn
  - Tăng `connection_pool_size=20`, `pool_timeout=20.0s`, `connect_timeout=30.0s`, `read_timeout=30.0s` khắc phục lỗi `telegram.error.TimedOut: Pool timeout`
- **Dependencies** (`api/requirements.txt`, `bot/requirements.txt`)
  - Cập nhật `respx==0.23.1` tương thích hoàn toàn với `httpx 0.28.1`

---

## [0.5.0] — 2026-09-27

### Added — Zerion Wallet Tracker

- **`ZerionClient`** (`bot/app/services/zerion_client.py`)
  - Kết nối Zerion API v1 qua Basic Auth (`zk_...` key)
  - `get_portfolio(address)` — tổng USD, 24h change, phân bổ theo chain
  - `get_positions(address, limit)` — top holdings với symbol, value, CA đầy đủ
  - `get_transactions(address, limit, operation_types)` — lịch sử giao dịch (swap, receive, send) với CA đầy đủ

- **`/wallet` command** (`bot/app/handlers/wallet.py`)
  - `/wallet <addr>` — portfolio overview: tổng USD, 24h change, top chains, top holdings với CA
  - `/wallet txs <addr>` — 10 giao dịch gần nhất; swap hiển thị token bán/mua + CA đầy đủ
  - `/wallet track <addr>` — subscribe theo dõi ví, notify khi có trade mới
  - `/wallet untrack <addr>` — bỏ theo dõi
  - `/wallet list` — danh sách ví đang theo dõi của chat

- **`wallet_tracking_job`** (`bot/app/jobs/wallet_tracking_job.py`)
  - Poll 5 phút: `GET /v1/wallets/{addr}/transactions/`
  - Diff theo tx hash; notify chỉ khi có hash mới
  - Notify đầy đủ: token name, CA đầy đủ, USD value, chain, timestamp

- **Config** — thêm `ZERION_API_KEY` vào `.env` và `Settings`

---

## [0.4.0] — 2026-09-27

### Added — Fomo Watching Alert

- **`get_following()`** (`FomoClient`) — gọi `GET /v2/leaderboard/following` trả danh sách `FollowedTrader`
- **`get_user_activity(user_id)`** (`FomoClient`) — gọi `GET /v2/users/{id}/activity` trả `TradeActivity` (id, symbol, CA, USD, type, timestamp)
- **`/fomo watching` command** — hiển thị danh sách following với PnL, trades, followers
- **`fomo_watching_alert_job`** (`bot/app/jobs/fomo_watching_alert.py`)
  - Poll 5 phút activity của từng followed trader
  - Seed lần đầu không notify; lần sau diff bằng activity `id`
  - Notify: token symbol, CA đầy đủ, network, USD volume, DEPOSIT/WITHDRAWAL direction, timestamp

### Fixed

- CA hiển thị đầy đủ (không truncate) ở tất cả messages — leaderboard alert, watching alert, wallet tracker

---

## [0.3.0] — 2026-09-27

### Fixed

- `fomo_leaderboard_alert_job` — Zerion API fix: slice `raw[:limit]` client-side vì API bỏ qua param `limit`
- `/fomo top` trả đúng 10 trader (trước đó trả 100)

---

## [0.2.0] — 2026-09-27

### Added — Fomo Leaderboard Alert

- **`FomoClient`** (`bot/app/services/fomo_client.py`)
  - HTTP client `prod-api.fomo.family` với Privy JWT auth
  - Header `User-Agent` browser bắt buộc (thiếu → 401)
  - `get_leaderboard(limit)` — trả `list[Trader]` với `top_holdings`
  - `is_token_expired()` — kiểm tra JWT `exp` bằng base64 decode
  - `FomoTokenExpiredError` — raised khi 401 hoặc JWT hết hạn

- **`/fomo` command** (`bot/app/handlers/fomo.py`)
  - `/fomo on` / `/fomo off` — subscribe/unsubscribe chat
  - `/fomo token <jwt>` — cập nhật Privy token runtime
  - `/fomo top` — hiển thị top 10 leaderboard ngay lập tức
  - `/fomo` — xem trạng thái (subscribed, token valid)

- **`fomo_leaderboard_alert_job`** (`bot/app/jobs/fomo_leaderboard_alert.py`)
  - Poll 5 phút: diff `_last_ranks` và `_last_holdings`
  - Notify: trader mới vào top N, rank nhảy ≥ 3, top-5 thêm holding mới
  - Token hết hạn → gửi cảnh báo cho tất cả subscribed chats

- **Config** — thêm `fomo_token: str = ""` vào `Settings`; pre-load client từ env khi startup

- **Help** — cập nhật `/help` text với section Fomo

---

## [0.1.0] — 2026-09-21

### Added — Initial Release

- **Token Search** (core feature)
  - Gửi địa chỉ contract EVM → bot trả báo cáo đầy đủ
  - `DexScreenerClient` — price, liquidity, volume 24h, DEX pairs
  - `GmGnClient` — top traders, smart money activity
  - `GoPlusClient` — security score, honeypot check, contract flags
  - `AnalysisService` — tổng hợp dữ liệu từ 3 nguồn
  - Hỗ trợ: Ethereum, BSC

- **Volume Alert**
  - `/alert on` / `/alert off` / `/alert` — subscribe/unsubscribe/status
  - `volume_alert_job` — poll 5 phút, scan token volume đột biến
  - Notify khi token vượt ngưỡng volume

- **FastAPI service** (`api/`)
  - `POST /api/v1/token/search` — endpoint token search
  - `GET /api/v1/health` — health check cho Docker healthcheck
  - Pydantic v2 schemas, structured logging

- **Infrastructure**
  - Docker Compose: `api` + `bot` services
  - `bot` depends on `api` healthy trước khi start
  - `.env.example` template

---

[Unreleased]: https://github.com/tqhoa/bot-meme/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/tqhoa/bot-meme/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/tqhoa/bot-meme/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/tqhoa/bot-meme/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/tqhoa/bot-meme/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/tqhoa/bot-meme/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/tqhoa/bot-meme/releases/tag/v0.1.0
