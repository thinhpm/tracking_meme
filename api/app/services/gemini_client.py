from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT_S = 300.0
_DEFAULT_MAX_RETRIES = 2


@dataclass
class GeminiClient:
    """Async LLM caller via the centralized LLM Gateway service."""

    base_url: str = ""
    provider: str = ""
    model: str = ""
    effort: str = ""
    timeout: float = field(default=_DEFAULT_TIMEOUT_S)
    max_retries: int = field(default=_DEFAULT_MAX_RETRIES)
    last_provider: str = ""
    last_model: str = ""

    def _get_service_url(self) -> str:
        """Resolve gateway base URL from instance property or environment variable."""
        url = self.base_url or os.getenv("GEMINI_SERVICE_URL") or "http://localhost:8000"
        return url.rstrip("/")

    async def run_text(
        self,
        prompt: str,
        images: list[Any] | None = None,
    ) -> str:
        """Call the centralized LLM Gateway service and return raw text."""
        url = f"{self._get_service_url()}/prompt"
        provider = self.provider or os.getenv("GEMINI_SERVICE_PROVIDER", "").strip()
        model = self.model or os.getenv("GEMINI_SERVICE_MODEL", "").strip()
        payload: dict[str, Any] = {
            "prompt": prompt,
            "model": model,
            "timeout": self.timeout,
        }
        if provider:
            payload["provider"] = provider
        if self.effort:
            payload["effort"] = self.effort
        if images:
            payload["images"] = images

        last_exc: Exception | None = None
        for attempt in range(1 + self.max_retries):
            if attempt > 0:
                log.warning(
                    "gemini_client_retry",
                    attempt=attempt,
                    max_retries=self.max_retries,
                    provider=provider or "(default)",
                    model=model or "(default)",
                )

            log.info(
                "calling_llm_gateway",
                provider=provider or "(default)",
                model=model or "(default)",
                prompt_len=len(prompt),
                attempt=attempt + 1,
            )

            try:
                async with httpx.AsyncClient(timeout=self.timeout + 15.0) as client:
                    resp = await client.post(url, json=payload)

                if resp.status_code == 502:
                    res_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    err_msg = res_data.get("error", resp.text[:500])
                    last_exc = RuntimeError(f"Gateway upstream error: {err_msg}")
                    log.warning(
                        "gateway_upstream_error",
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        error=str(last_exc),
                    )
                    await asyncio.sleep(3.0 * (attempt + 1))
                    continue

                if resp.status_code != 200:
                    last_exc = RuntimeError(
                        f"Gateway error (status={resp.status_code}): {resp.text[:500]}"
                    )
                    log.error("gateway_http_error", status_code=resp.status_code, error=str(last_exc))
                    continue

                res_data = resp.json()
                if "error" in res_data:
                    last_exc = RuntimeError(f"Gateway error: {res_data['error']}")
                    log.error("gateway_response_error", error=str(last_exc))
                    continue

                raw = res_data.get("text", "").strip()
                self.last_provider = res_data.get("provider", "unknown")
                self.last_model = res_data.get("model", self.model)
                log.info(
                    "llm_response_received",
                    provider=self.last_provider,
                    model=self.last_model,
                    length=len(raw),
                )

                # Strip <think>...</think> reasoning blocks
                raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                return raw

            except Exception as e:
                last_exc = e
                log.error("llm_gateway_exception", error=repr(e))

            if attempt < self.max_retries:
                await asyncio.sleep(2.0 * attempt)

        raise last_exc if last_exc is not None else RuntimeError("Gateway request failed")

    async def run_json(
        self,
        prompt: str,
        images: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Call LLM Gateway service and parse response as JSON."""
        raw = await self.run_text(prompt, images=images)

        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to find the outermost JSON object
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    pass

        raise RuntimeError(
            f"Could not parse LLM output as JSON.\nRaw (first 800 chars):\n{raw[:800]}"
        )


# Alias as AsyncGeminiCLI for direct compatibility
AsyncGeminiCLI = GeminiClient
