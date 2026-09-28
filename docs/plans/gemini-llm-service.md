# Plan: LLM Gemini Service Integration

**Spec**: `docs/specs/gemini-llm-service.md`  
**Layer**: Backend (FastAPI API service)

---

## Phase 1: Foundation & Configuration

- [x] **Task 1.1**: Update API configuration and environment definitions
  - **Files**:
    - `api/app/config.py`
    - `.env.example`
  - **Details**:
    - Make `anthropic_api_key: str = ""` optional in `Settings`.
    - Add `gemini_service_url: str = "http://localhost:8000"`.
    - Add `gemini_service_provider: str = ""`.
    - Add `gemini_service_model: str = ""`.
    - Update `.env.example` with comments explaining that if `ANTHROPIC_API_KEY` is empty, the Gemini service gateway is used.
  - **Acceptance Criteria**:
    - `Settings()` instantiates without error when `ANTHROPIC_API_KEY` is unset or empty.
    - Default Gemini settings resolve correctly.

---

## Checkpoint: Foundation Complete

**Verify before proceeding**:
- [x] `Settings()` instantiates with and without `ANTHROPIC_API_KEY`.
- [x] Existing configuration unit tests pass.

---

## Phase 2: Gemini Client Implementation (TDD)

- [x] **Task 2.1**: Implement `GeminiClient` (AsyncGeminiCLI)
  - **Files**:
    - `api/app/services/gemini_client.py`
    - `api/tests/unit/services/test_gemini_client.py`
  - **Test First (RED)**:
    - Write unit tests mocking `httpx.AsyncClient`:
      - Successful text response.
      - Stripping `<think>...</think>` reasoning tags.
      - Stripping markdown code blocks (` ```json ... ``` `) and parsing valid JSON.
      - Parsing substring JSON when output contains surrounding text.
      - Retrying on 502 status with backoff.
      - Raising `RuntimeError` on non-200 / gateway error responses.
  - **Implement (GREEN)**:
    - Create `GeminiClient` matching `gemini_cli.py` specification with `run_text` and `run_json`.
    - Use `httpx.AsyncClient` with timeout and retries.
  - **Refactor**:
    - Clean typing annotations and error logging.
  - **Acceptance Criteria**:
    - All tests in `test_gemini_client.py` pass.
    - Test coverage for `gemini_client.py` ≥ 90% (achieved: 98%).

---

## Checkpoint: Gemini Client Complete

**Verify before proceeding**:
- [x] `pytest api/tests/unit/services/test_gemini_client.py` passes 100%.
- [x] Handles malformed JSON and upstream errors cleanly.

---

## Phase 3: AnalysisService Multi-Provider Integration (TDD)

- [x] **Task 3.1**: Update `AnalysisService` to support Gemini and conditional routing
  - **Files**:
    - `api/app/services/analysis_service.py`
    - `api/tests/unit/services/test_analysis_service.py`
  - **Test First (RED)**:
    - Add test cases in `test_analysis_service.py`:
      - `test_uses_claude_when_anthropic_key_present`: verifies `_call_claude` is used when `api_key` is provided.
      - `test_uses_gemini_when_anthropic_key_empty`: verifies `gemini_client.run_json` is used when `api_key` is empty.
      - `test_gemini_failure_falls_back_to_heuristic`: verifies `heuristic_analysis` is returned if `gemini_client` raises an error.
  - **Implement (GREEN)**:
    - Update `AnalysisService.__init__(self, api_key: str = "", gemini_client: GeminiClient | None = None)`.
    - Implement `_call_gemini(self, market: dict, security: dict, social: dict) -> dict`.
    - Route in `generate`: if `self._api_key` -> Claude, else -> Gemini (or heuristic if no client provided).
  - **Refactor**:
    - Keep fallback catch block comprehensive and robust.
  - **Acceptance Criteria**:
    - All unit tests pass.

- [x] **Task 3.2**: Update route service builder for dependency injection
  - **Files**:
    - `api/app/routes/token.py`
  - **Details**:
    - Update `_build_service()` to instantiate `GeminiClient` when `settings.anthropic_api_key` is falsy, and inject into `AnalysisService`.
  - **Acceptance Criteria**:
    - Token search route seamlessly uses Gemini gateway when `ANTHROPIC_API_KEY` is empty.

---

## Checkpoint: Service Integration Complete

**Verify before proceeding**:
- [x] `pytest api/tests` passes all unit and integration tests.
- [x] `AnalysisService` correctly branches based on API key presence.

---

## Phase 4: Verification & Coverage Audit

- [x] **Task 4.1**: Full test suite execution and coverage audit
  - Run `pytest api/tests --cov=app --cov-report=term-missing`
  - Ensure total coverage ≥ 80% (achieved: 92.11%).
  - Verify static type check / linting consistency.
