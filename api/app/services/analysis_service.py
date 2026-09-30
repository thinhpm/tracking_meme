from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import anthropic
import structlog

if TYPE_CHECKING:
    from app.services.gemini_client import GeminiClient

log = structlog.get_logger(__name__)

_PROMPT_TEMPLATE = """Bạn là chuyên gia phân tích rủi ro token crypto. Phân tích dữ liệu sau và trả lời bằng JSON.

Dữ liệu thị trường:
{market_json}

Dữ liệu security:
{security_json}

Dữ liệu mạng xã hội:
{social_json}

Trả về JSON với đúng cấu trúc sau (không có markdown, chỉ JSON thuần):
{{
  "risk_flags": ["<cảnh báo rủi ro bằng tiếng Việt>", ...],
  "positive_flags": ["<điểm tích cực bằng tiếng Việt>", ...],
  "summary": "<1 câu nhận định ngắn bằng tiếng Việt>",
  "risk_level": "<LOW|MEDIUM|HIGH|VERY_HIGH>"
}}"""


class AnalysisService:
    def __init__(self, api_key: str = "", gemini_client: GeminiClient | None = None) -> None:
        self._api_key = api_key.strip()
        self._client: anthropic.AsyncAnthropic | None = (
            anthropic.AsyncAnthropic(api_key=self._api_key) if self._api_key else None
        )
        self._gemini = gemini_client

    async def generate(self, market: dict, security: dict | None, social: dict) -> dict:
        sec = security or {}
        try:
            if self._client:
                return await self._call_claude(market, sec, social)
            if self._gemini:
                return await self._call_gemini(market, sec, social)
            log.warning("no_llm_provider_configured_fallback_heuristic")
            return heuristic_analysis(market, sec, social)
        except Exception as e:
            log.warning("llm_analysis_failed_fallback_heuristic", error=str(e))
            return heuristic_analysis(market, sec, social)

    async def _call_claude(self, market: dict, security: dict, social: dict) -> dict:
        assert self._client is not None
        prompt = _PROMPT_TEMPLATE.format(
            market_json=json.dumps(market, ensure_ascii=False),
            security_json=json.dumps(security, ensure_ascii=False),
            social_json=json.dumps(social, ensure_ascii=False),
        )
        message = await self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()  # type: ignore[index]
        return json.loads(text)

    async def _call_gemini(self, market: dict, security: dict, social: dict) -> dict:
        assert self._gemini is not None
        prompt = _PROMPT_TEMPLATE.format(
            market_json=json.dumps(market, ensure_ascii=False),
            security_json=json.dumps(security, ensure_ascii=False),
            social_json=json.dumps(social, ensure_ascii=False),
        )
        return await self._gemini.run_json(prompt)


def heuristic_analysis(market: dict, security: dict, social: dict) -> dict:
    risk_flags: list[str] = []
    positive_flags: list[str] = []

    mcap = market.get("market_cap") or 0
    vol_24h = (market.get("volume") or {}).get("h24") or 0
    liquidity = market.get("liquidity_usd") or 0
    price_change_24h = (market.get("price_change") or {}).get("h24") or 0
    buys = (market.get("txns_h24") or {}).get("buys") or 0
    sells = (market.get("txns_h24") or {}).get("sells") or 0

    is_honeypot = security.get("is_honeypot")
    buy_tax = security.get("buy_tax") or 0
    sell_tax = security.get("sell_tax") or 0
    lp_locked = security.get("lp_locked")

    website = (social or {}).get("website")

    if is_honeypot:
        risk_flags.append("🚨 Honeypot được phát hiện — không thể bán token")
        return {
            "risk_flags": risk_flags,
            "positive_flags": [],
            "summary": "Token là honeypot. Tuyệt đối không mua.",
            "risk_level": "VERY_HIGH",
        }

    if mcap > 0 and vol_24h > mcap * 5:
        ratio = round(vol_24h / mcap, 1)
        risk_flags.append(f"Volume 24h gấp ~{ratio}x MCap — dấu hiệu pump/dump")

    if liquidity < 50_000:
        risk_flags.append(f"Liquidity thấp ${liquidity:,.0f} — dễ slippage cao")

    if price_change_24h > 1000:
        risk_flags.append(f"Giá tăng +{price_change_24h:,.0f}% trong 24h — có thể đang ở vùng đỉnh")

    if buy_tax > 10 or sell_tax > 10:
        risk_flags.append(f"Thuế cao: mua {buy_tax}% / bán {sell_tax}%")

    if lp_locked is False:
        risk_flags.append("LP chưa lock — nguy cơ rug pull")

    if not website:
        risk_flags.append("Không có website chính thức")

    total_txns = buys + sells
    if total_txns > 0:
        sell_ratio = sells / total_txns
        if sell_ratio < 0.6:
            positive_flags.append(f"Tỉ lệ buy/sell cân bằng ({buys:,}/{sells:,})")

    if total_txns > 5000:
        positive_flags.append(f"Volume thực với {total_txns:,} giao dịch/24h")

    risk_count = len(risk_flags)
    if is_honeypot or risk_count >= 4:
        level = "VERY_HIGH"
    elif risk_count >= 2:
        level = "HIGH"
    elif risk_count == 1:
        level = "MEDIUM"
    else:
        level = "LOW"

    summary = _build_summary(level, risk_flags)

    return {
        "risk_flags": risk_flags,
        "positive_flags": positive_flags,
        "summary": summary,
        "risk_level": level,
    }


def _build_summary(level: str, risk_flags: list[str]) -> str:
    if level == "VERY_HIGH":
        return "Token cực kỳ rủi ro. Không nên tham gia."
    if level == "HIGH":
        return f"Token rủi ro cao. {risk_flags[0] if risk_flags else ''}"
    if level == "MEDIUM":
        return "Token có một số dấu hiệu cần chú ý. Cân nhắc kỹ trước khi vào lệnh."
    return "Token có vẻ ổn định ở thời điểm phân tích."
