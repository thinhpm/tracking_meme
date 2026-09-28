# Feature: LLM Gemini Service Integration

## Objective

Add support for a centralized LLM Gateway service (Gemini service) as an alternative to Anthropic Claude for generating token risk analysis reports. If `ANTHROPIC_API_KEY` is omitted or empty, the API service automatically routes LLM prompts to the centralized Gemini gateway service.

## Target Users

- Developers and system operators running the token search API who prefer or need to use the centralized LLM gateway (`gemini_service.py`) without incurring Anthropic API costs or requiring an Anthropic API key.
- End users on Telegram, who continue receiving token risk analysis without degradation of service.

## Layer

- [x] Backend only (FastAPI) — `api` service
- [ ] Frontend only (Vue 3)
- [ ] Full-stack (FastAPI + Vue 3)

---

## Core Features & Acceptance Criteria

| # | Feature | Acceptance Criteria |
|---|---------|---------------------|
| 1 | **Conditional LLM Provider Selection** | If `ANTHROPIC_API_KEY` is present and non-empty, use Anthropic Claude. If `ANTHROPIC_API_KEY` is empty or missing, route prompts to the centralized Gemini service gateway. |
| 2 | **Reusable Async Gemini Client** | Implement `GeminiClient` (mirroring `AsyncGeminiCLI` from `gemini_cli.py`) with async `run_text` and `run_json` methods using `httpx.AsyncClient`. |
| 3 | **Configurable Gateway Settings** | `Settings` in `api/app/config.py` makes `anthropic_api_key` optional (defaults to `""`), and introduces `gemini_service_url` (default: `http://localhost:8000`), `gemini_service_provider` (optional), and `gemini_service_model` (optional). |
| 4 | **Robust Output Sanitization** | Filter reasoning blocks (`<think>...</think>`), strip markdown code fences (` ```json `), and extract outermost JSON structures from the gateway response. |
| 5 | **Gateway Retry & Error Resilience** | Retry transient 502 / network failures with exponential backoff up to `max_retries` (default: 2). |
| 6 | **Graceful Heuristic Fallback** | If the active LLM provider (Anthropic or Gemini Gateway) encounters an unrecoverable failure or timeout, gracefully fall back to `heuristic_analysis` without raising a 500 error to the client. |
| 7 | **Unit & Integration Test Coverage** | Comprehensive unit tests for `GeminiClient` and updated tests for `AnalysisService` with mocked HTTP responses and fallback scenarios (≥ 80% coverage). |

---

## Out of Scope

- Modifying the Telegram `bot` service (the contract between `bot` and `api` remains unchanged).
- Deploying or hosting the external `gemini_service.py` within this repo (it is treated as an external gateway service).
- Streaming LLM token responses (the analysis endpoint returns structured JSON once complete).
- Direct Google Gemini SDK dependencies (the gateway protocol uses standard HTTP REST via `httpx`).

---

## Technical Approach

### 1. Configuration Changes (`api/app/config.py`)

Update `Settings` with optional fields:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    gemini_service_url: str = "http://localhost:8000"
    gemini_service_provider: str = ""
    gemini_service_model: str = ""
    goplus_api_key: str = ""
    log_level: str = "info"
    environment: str = "development"
```

### 2. Gemini Client (`api/app/services/gemini_client.py`)

Adapted from `gemini_cli.py`:
- Target endpoint: `POST {gemini_service_url}/prompt`
- Payload structure:
  ```json
  {
    "prompt": "<prompt_text>",
    "model": "<optional_model>",
    "provider": "<optional_provider>",
    "timeout": 300.0
  }
  ```
- Handles HTTP timeouts, status code checking, retry on 502 / network failure.
- Output cleaning:
  - Regex removal of `<think>.*?</think>`
  - Code fence stripping (` ```json ... ``` `)
  - Substring JSON decoding fallback `{ ... }`
- Provides `run_json(prompt: str) -> dict[str, Any]` and `run_text(prompt: str) -> str`.

### 3. Analysis Service Integration (`api/app/services/analysis_service.py`)

Refactor `AnalysisService` to support dual providers:
- `__init__(self, api_key: str = "", gemini_client: GeminiClient | None = None)`
- Provider resolution:
  - If `bool(api_key.strip())`: provider is `Anthropic` (`claude-haiku-4-5-20251001`).
  - Else: provider is `Gemini` (calls `gemini_client.run_json(prompt)`).
- Both routes use the existing `_PROMPT_TEMPLATE`.
- If LLM call fails, catches `Exception` and executes `heuristic_analysis(market, security, social)`.

### 4. Dependency Injection / Route Wiring (`api/app/routes/token.py`)

Update `_build_service()`:
```python
def _build_service() -> TokenService:
    settings = get_settings()
    gemini_client = None
    if not settings.anthropic_api_key:
        gemini_client = GeminiClient(
            base_url=settings.gemini_service_url,
            provider=settings.gemini_service_provider,
            model=settings.gemini_service_model,
        )

    analysis_svc = AnalysisService(
        api_key=settings.anthropic_api_key,
        gemini_client=gemini_client,
    )

    return TokenService(
        gmgn=GmgnClient(),
        dex=DexScreenerClient(),
        goplus=GoplusClient(api_key=settings.goplus_api_key),
        analysis=analysis_svc,
    )
```

### 5. Environment Variables & Documentation

Update `.env.example`:
```bash
# API service
ANTHROPIC_API_KEY=              # optional — if empty, Gemini service gateway will be used
GEMINI_SERVICE_URL=http://localhost:8000  # Gateway service base URL
GEMINI_SERVICE_PROVIDER=         # optional — e.g. openrouter, 9router, gemini
GEMINI_SERVICE_MODEL=            # optional — e.g. gemini-2.5-flash
GOPLUS_API_KEY=                  # optional — leave empty for free tier
LOG_LEVEL=info
ENVIRONMENT=development
```

> [!NOTE]
> When running the API inside Docker while `gemini_service.py` is running on the host machine, set `GEMINI_SERVICE_URL=http://host.docker.internal:8000`.

---

## Mandatory Standards

- Rules: `.claude/rules/` — all mandatory (`clean-code.md`, `code-style.md`, `error-handling.md`).
- Async I/O: Use `httpx.AsyncClient` for all external gateway network calls.
- Strict typing: Full type annotations on all signatures (`typing.Any`, `dict[str, Any]`, `Optional`, etc.).
- Logging: Use structured logging (`logging.getLogger(__name__)`).

---

## Testing Strategy

### Unit Tests
1. **`test_gemini_client.py`**:
   - `test_run_text_success`: Mock 200 HTTP response, verify cleaned text.
   - `test_run_text_removes_think_tags`: Verify `<think>reasoning</think>` is filtered out.
   - `test_run_json_extracts_markdown_fence`: Verify JSON inside ` ```json ... ``` ` is decoded.
   - `test_run_json_extracts_substring_object`: Verify JSON embedded in arbitrary text is decoded.
   - `test_retry_on_502_upstream_error`: Verify retries on 502 with eventual success or raised exception.
   - `test_gateway_error_raises_runtime_error`: Non-200 responses raise appropriate `RuntimeError`.

2. **`test_analysis_service.py`**:
   - `test_uses_anthropic_when_api_key_provided`: Mock Anthropic client, verify it is invoked.
   - `test_uses_gemini_when_anthropic_api_key_empty`: Mock `GeminiClient`, verify `run_json` is invoked.
   - `test_gemini_failure_falls_back_to_heuristic`: Mock `gemini_client.run_json` raising exception, verify `heuristic_analysis` is returned.

### Target Coverage
- `GeminiClient`: ≥ 90%
- `AnalysisService`: ≥ 85%

---

## Boundaries

### Always Do
- Keep `heuristic_analysis` as the reliable fallback when LLM requests fail or return invalid JSON.
- Maintain full backward compatibility for users who still define `ANTHROPIC_API_KEY`.
- Sanitize response text (strip `<think>` tags and markdown code blocks) before JSON deserialization.

### Ask First
- Changing the default `GEMINI_SERVICE_URL` or default model parameters.
- Removing or altering the heuristic fallback algorithm.

### Never Do
- Never block the asyncio event loop with synchronous network calls.
- Never crash the `/api/v1/token/search` endpoint if the LLM gateway is offline or unresponsive.
- Never commit actual API keys or gateway secrets into code or version control.
