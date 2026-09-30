from unittest.mock import patch

import httpx
import pytest
import respx

from app.services.gemini_client import GeminiClient

_BASE_URL = "http://localhost:8000"


@respx.mock
async def test_run_text_success() -> None:
    respx.post(f"{_BASE_URL}/prompt").mock(
        return_value=httpx.Response(
            200,
            json={"text": "Analysis complete", "provider": "gemini", "model": "gemini-2.5-flash"},
        )
    )
    client = GeminiClient(base_url=_BASE_URL)
    result = await client.run_text("Analyze token")
    assert result == "Analysis complete"
    assert client.last_provider == "gemini"
    assert client.last_model == "gemini-2.5-flash"


@respx.mock
async def test_run_text_strips_think_tags() -> None:
    respx.post(f"{_BASE_URL}/prompt").mock(
        return_value=httpx.Response(
            200,
            json={"text": "<think>reasoning step 1\nstep 2</think>Clean response text"},
        )
    )
    client = GeminiClient(base_url=_BASE_URL)
    result = await client.run_text("Prompt")
    assert result == "Clean response text"


@respx.mock
async def test_run_json_valid_json() -> None:
    respx.post(f"{_BASE_URL}/prompt").mock(
        return_value=httpx.Response(
            200,
            json={"text": '{"risk_flags": ["high tax"], "risk_level": "HIGH"}'},
        )
    )
    client = GeminiClient(base_url=_BASE_URL)
    result = await client.run_json("Prompt")
    assert result == {"risk_flags": ["high tax"], "risk_level": "HIGH"}


@respx.mock
async def test_run_json_strips_markdown_code_fence() -> None:
    raw_markdown = '```json\n{"summary": "Token looks fine", "risk_level": "LOW"}\n```'
    respx.post(f"{_BASE_URL}/prompt").mock(
        return_value=httpx.Response(200, json={"text": raw_markdown})
    )
    client = GeminiClient(base_url=_BASE_URL)
    result = await client.run_json("Prompt")
    assert result["summary"] == "Token looks fine"
    assert result["risk_level"] == "LOW"


@respx.mock
async def test_run_json_extracts_substring_json() -> None:
    surrounded = 'Note from model:\n{"summary": "Caution advised", "risk_level": "MEDIUM"}\nEnd note.'
    respx.post(f"{_BASE_URL}/prompt").mock(
        return_value=httpx.Response(200, json={"text": surrounded})
    )
    client = GeminiClient(base_url=_BASE_URL)
    result = await client.run_json("Prompt")
    assert result["summary"] == "Caution advised"
    assert result["risk_level"] == "MEDIUM"


@respx.mock
async def test_run_json_raises_on_invalid_json() -> None:
    respx.post(f"{_BASE_URL}/prompt").mock(
        return_value=httpx.Response(200, json={"text": "Not a valid json response"})
    )
    client = GeminiClient(base_url=_BASE_URL)
    with pytest.raises(RuntimeError, match="Could not parse LLM output as JSON"):
        await client.run_json("Prompt")


@respx.mock
async def test_retry_on_502_upstream_error() -> None:
    route = respx.post(f"{_BASE_URL}/prompt")
    route.side_effect = [
        httpx.Response(502, json={"error": "Bad gateway upstream"}),
        httpx.Response(200, json={"text": '{"ok": true}'}),
    ]
    client = GeminiClient(base_url=_BASE_URL, max_retries=1)
    with patch("asyncio.sleep", return_value=None):
        result = await client.run_json("Prompt")
    assert result == {"ok": True}


@respx.mock
async def test_non_200_error_response_raises() -> None:
    respx.post(f"{_BASE_URL}/prompt").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    client = GeminiClient(base_url=_BASE_URL, max_retries=0)
    with pytest.raises(RuntimeError, match="Gateway error"):
        await client.run_text("Prompt")


@respx.mock
async def test_payload_structure_and_overrides() -> None:
    route = respx.post(f"{_BASE_URL}/prompt").mock(
        return_value=httpx.Response(200, json={"text": "done"})
    )
    client = GeminiClient(
        base_url=_BASE_URL,
        provider="openrouter",
        model="gemini-2.5-flash",
        effort="high",
        timeout=60.0,
    )
    await client.run_text("test prompt")
    assert route.called
    sent_payload = route.calls.last.request.read()
    import json
    data = json.loads(sent_payload)
    assert data["prompt"] == "test prompt"
    assert data["provider"] == "openrouter"
    assert data["model"] == "gemini-2.5-flash"
    assert data["effort"] == "high"
    assert data["timeout"] == 60.0


@respx.mock
async def test_run_text_with_error_in_json_response() -> None:
    respx.post(f"{_BASE_URL}/prompt").mock(
        return_value=httpx.Response(200, json={"error": "model overload"})
    )
    client = GeminiClient(base_url=_BASE_URL, max_retries=0)
    with pytest.raises(RuntimeError, match="Gateway error: model overload"):
        await client.run_text("Prompt")


@respx.mock
async def test_run_text_network_exception_retry() -> None:
    route = respx.post(f"{_BASE_URL}/prompt")
    route.side_effect = [
        httpx.ConnectError("Connection refused"),
        httpx.Response(200, json={"text": "recovered"}),
    ]
    client = GeminiClient(base_url=_BASE_URL, max_retries=1)
    with patch("asyncio.sleep", return_value=None):
        result = await client.run_text("Prompt")
    assert result == "recovered"


@respx.mock
async def test_run_text_with_images_payload() -> None:
    route = respx.post(f"{_BASE_URL}/prompt").mock(
        return_value=httpx.Response(200, json={"text": "image analyzed"})
    )
    client = GeminiClient(base_url=_BASE_URL)
    result = await client.run_text("Prompt", images=["base64-img-data"])
    assert result == "image analyzed"
    import json
    data = json.loads(route.calls.last.request.read())
    assert data["images"] == ["base64-img-data"]


def test_service_url_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_SERVICE_URL", "http://env-host:9999/")
    client = GeminiClient()
    assert client._get_service_url() == "http://env-host:9999"

