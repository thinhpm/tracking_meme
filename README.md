# bot-meme

Telegram bot theo dõi crypto — tìm kiếm token, cảnh báo volume, theo dõi leaderboard fomo.family, và tracking ví onchain qua Zerion.

## Kiến trúc

```
bot-meme/
├── api/          FastAPI — token search, phân tích onchain
└── bot/          Python Telegram Bot — commands, jobs, alerts
```

Hai service chạy Docker Compose. Bot gọi API qua HTTP nội bộ (`http://api:8000`).

```
Telegram → Bot → FastAPI → DexScreener / GmGn / GoPlus
                FastAPI → LLM Analysis (Gemini Gateway Service / Claude)
                Bot → fomo.family API (Privy JWT)
                Bot → Zerion API (Basic Auth)
```

## Tech Stack

| Layer | Tool |
|---|---|
| Bot framework | python-telegram-bot 21.9 + job-queue (APScheduler) |
| HTTP client | httpx (async) |
| Config | pydantic-settings |
| API framework | FastAPI + uvicorn |
| LLM Analysis | Gemini Gateway Service (mặc định) / Anthropic Claude |
| Container | Docker Compose |

## Quick Start

```bash
cp .env.example .env
# Điền các key cần thiết vào .env
docker compose up -d
docker compose logs -f bot
```

## Cấu hình `.env`

```env
# API service
ANTHROPIC_API_KEY=               # optional — nếu để trống sẽ tự động dùng Gemini service
GEMINI_SERVICE_URL=http://localhost:8000 # LLM Gateway URL
GEMINI_SERVICE_PROVIDER=ninerouter       # optional — e.g. ninerouter, openrouter
GEMINI_SERVICE_MODEL=groq-cli            # optional — e.g. groq-cli, gemini-2.5-flash
GOPLUS_API_KEY=                  # optional — free tier nếu để trống
LOG_LEVEL=info
ENVIRONMENT=development

# Bot service
TELEGRAM_BOT_TOKEN=...           # BotFather token
API_BASE_URL=http://api:8000
ZERION_API_KEY=                  # từ app.zerion.io/developer
FOMO_TOKEN=                      # Privy JWT từ fomo.family (1 giờ / lần)
```

---

## Deploy Production (Raspberry Pi)

Cấu hình `docker-compose.yml` có sẵn 2 service riêng (`api-prod`, `bot-prod`) tối ưu cho Raspberry Pi / Production server:
- Không map port API ra ngoài host (chỉ giao tiếp nội bộ container).
- Tự động map `host.docker.internal` để kết nối tới Gemini Gateway service chạy trên host Pi (`http://host.docker.internal:8000`).
- Cấu hình DNS (`8.8.8.8`, `1.1.1.1`) và log rotation (`10m`) tránh tràn thẻ nhớ SD.

```bash
# Khởi chạy trên Pi
docker compose up -d --build api-prod bot-prod

# Xem logs
docker compose logs -f api-prod bot-prod

# Dừng service
docker compose stop api-prod bot-prod
```

---

## Commands

### Token Search

Gửi địa chỉ contract EVM bất kỳ (hoặc kèm text), bot tra cứu và trả báo cáo.

```
0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48
Kiểm tra token này: 0xA0b86991...
```

**Dữ liệu trả về:** tên, symbol, price, market cap, volume 24h, liquidity, security score (GoPlus), holders, top traders (GmGn), DexScreener links, phân tích rủi ro bằng AI (Gemini/Claude).

Hỗ trợ: Ethereum, BSC.

---

### Volume Alert

Tự động cảnh báo các token có volume đột biến mỗi 5 phút.

```
/alert on     — bật thông báo
/alert off    — tắt thông báo
/alert        — xem trạng thái
```

---

### Fomo Leaderboard Alert

Theo dõi leaderboard top trader trên [fomo.family](https://fomo.family). Thông báo khi:
- Trader mới lọt vào top 10
- Rank nhảy ≥ 3 bậc
- Top 5 trader thêm holding mới

```
/fomo on                  — bật alert
/fomo off                 — tắt alert
/fomo top                 — xem top 10 leaderboard ngay
/fomo token <jwt>         — cập nhật Privy token (hết hạn sau 1 giờ)
/fomo                     — xem trạng thái
```

> **Lưu ý:** Privy JWT hết hạn sau 1 giờ. Lấy token mới tại fomo.family (F12 → Network → bất kỳ request → header `Authorization: Bearer ...`).

---

### Fomo Watching Alert

Theo dõi giao dịch của những trader đang follow trên fomo.family. Thông báo mỗi khi họ mua/bán token (poll 5 phút).

```
/fomo watching            — xem danh sách đang follow
```

**Notify format:**
```
🔔 Trade mới từ following

👤 picametalica — 🟢 Mua COIN
🌐 Chain: Monad
🪙 Token: COIN
📋 CA: `0x6330d8c3178a418788df01a47479c0ce7ccf450b`
💰 Volume: $1.52
⏰ 2026-09-27 01:16 UTC
```

Yêu cầu: token Privy hợp lệ (set qua `/fomo token`).

---

### Wallet Tracker (Zerion)

Tra cứu và theo dõi ví onchain qua Zerion API. Hỗ trợ tất cả chain Zerion index (Ethereum, BSC, Base, Arbitrum, Solana, ...).

```
/wallet <addr>            — portfolio overview
/wallet txs <addr>        — 10 giao dịch gần nhất
/wallet track <addr>      — theo dõi ví (notify khi có trade mới)
/wallet untrack <addr>    — bỏ theo dõi
/wallet list              — danh sách ví đang theo dõi
```

**Portfolio output:**
```
💼 Wallet `0x47ac...6D503`

💰 Tổng: $11.00B
📈 24h: +$3.62M (+0.03%)
🌐 Chains: ethereum: $11.00B | sonic: $456K | base: $39K

🪙 Top Holdings:
  • USDC $5,200,000
    📋 `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48`
```

**Trade notify format:**
```
🔔 Trade mới — `0x47ac...6D503`

🔄 Swap
  📤 Bán ETH $1,234
     CA: `0x9d4c2d93ae258ddc37d415ef2ab41a25fbacc34a`
  📥 Mua JOKER $2,504
     CA: `0x3c3ac4b67e0bc21c4c0a24e0ff5f84f7ee072224`
🌐 Chain: base
⏰ 04/10 03:51 UTC
```

---

## Background Jobs

| Job | Interval | Mô tả |
|---|---|---|
| `volume_alert_job` | 5 phút | Scan token volume đột biến |
| `fomo_leaderboard_alert_job` | 5 phút | Diff leaderboard fomo.family |
| `fomo_watching_alert_job` | 5 phút | Poll activity của following |
| `wallet_tracking_job` | 5 phút | Poll txs của ví đang track |

---

## API Endpoints (FastAPI)

```
POST /api/v1/token/search    — tìm kiếm token theo CA
GET  /api/v1/health          — health check
```

---

## Development

```bash
# Chạy local không Docker
cd bot && pip install -r requirements.txt
# set .env rồi:
python -m app.main

# Test
cd bot && pytest
cd api && pytest
```
