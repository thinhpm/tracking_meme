"""Solana WebSocket event listener for realtime Raydium & Pump.fun DEX swaps."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Callable, NamedTuple

import websockets

logger = logging.getLogger(__name__)

PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

_PUMP_USER_RE = re.compile(r"user=([a-zA-Z0-9_-]+)")
_PUMP_MINT_RE = re.compile(r"mint=([a-zA-Z0-9_-]+)")
_PUMP_SOL_AMT_RE = re.compile(r"sol_amount=(\d+)")

_RAY_USER_RE = re.compile(r"user=([a-zA-Z0-9_-]+)")
_RAY_MINT_RE = re.compile(r"mint=([a-zA-Z0-9_-]+)")


class SolanaSwapEvent(NamedTuple):
    signature: str
    dex: str  # "pump_fun" | "raydium" | "unknown"
    mint: str
    user_wallet: str
    is_buy: bool
    amount_usd: float
    timestamp: float


def parse_pump_fun_log(logs: list[str], signature: str) -> SolanaSwapEvent | None:
    if not any(PUMP_FUN_PROGRAM in line for line in logs):
        return None

    is_buy = any("Instruction: Buy" in line for line in logs)
    is_sell = any("Instruction: Sell" in line for line in logs)
    if not (is_buy or is_sell):
        return None

    user = ""
    mint = ""
    sol_amount = 0.0

    for line in logs:
        if not user:
            m = _PUMP_USER_RE.search(line)
            if m:
                user = m.group(1)
        if not mint:
            m = _PUMP_MINT_RE.search(line)
            if m:
                mint = m.group(1)
        if sol_amount == 0.0:
            m = _PUMP_SOL_AMT_RE.search(line)
            if m:
                sol_amount = float(m.group(1)) / 1e9

    if not (user and mint):
        return None

    # Estimate USD value assuming SOL ~ $150 if amount present
    est_usd = sol_amount * 150.0

    return SolanaSwapEvent(
        signature=signature,
        dex="pump_fun",
        mint=mint,
        user_wallet=user,
        is_buy=is_buy,
        amount_usd=est_usd,
        timestamp=time.time(),
    )


def parse_raydium_log(logs: list[str], signature: str) -> SolanaSwapEvent | None:
    if not any(RAYDIUM_AMM_PROGRAM in line for line in logs):
        return None

    is_swap = any("Instruction: Swap" in line for line in logs)
    if not is_swap:
        return None

    user = ""
    mint = ""
    for line in logs:
        if not user:
            m = _RAY_USER_RE.search(line)
            if m:
                user = m.group(1)
        if not mint:
            m = _RAY_MINT_RE.search(line)
            if m:
                mint = m.group(1)

    if not (user and mint):
        return None

    return SolanaSwapEvent(
        signature=signature,
        dex="raydium",
        mint=mint,
        user_wallet=user,
        is_buy=True,  # Default to buy in AMM swap base in
        amount_usd=0.0,
        timestamp=time.time(),
    )


def parse_solana_log_notification(value: dict) -> SolanaSwapEvent | None:
    signature = value.get("signature", "")
    logs = value.get("logs", [])
    if not logs:
        return None

    event = parse_pump_fun_log(logs, signature)
    if event:
        return event

    event = parse_raydium_log(logs, signature)
    if event:
        return event

    return None


class SolanaEventListener:
    """Manages WebSocket connection to Solana RPC and listens for DEX swaps."""

    def __init__(
        self,
        ws_url: str,
        tracked_wallets: set[str] | None = None,
        on_swap_callback: Callable | None = None,
        max_reconnect_attempts: int = 5,
        initial_backoff_seconds: float = 1.0,
        backoff_multiplier: float = 2.0,
    ) -> None:
        self.ws_url = ws_url
        self.tracked_wallets: set[str] = tracked_wallets or set()
        self.on_swap_callback = on_swap_callback
        self.max_reconnect_attempts = max_reconnect_attempts
        self.initial_backoff_seconds = initial_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        self.reconnect_attempts = 0
        self._running = False

    def add_tracked_wallet(self, address: str) -> None:
        self.tracked_wallets.add(address)

    def is_tracked(self, wallet: str) -> bool:
        return wallet in self.tracked_wallets

    async def handle_log_notification(self, value: dict) -> SolanaSwapEvent | None:
        event = parse_solana_log_notification(value)
        if not event:
            return None

        # Filter by tracked wallets if list is configured
        if self.tracked_wallets and not self.is_tracked(event.user_wallet):
            return None

        if self.on_swap_callback:
            try:
                res = self.on_swap_callback(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error("solana_listener.callback_error", extra={"error": str(e)})

        return event

    async def connect_and_listen(self) -> None:
        self._running = True
        backoff = self.initial_backoff_seconds

        while self._running and self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("solana_listener.connected", extra={"url": self.ws_url})
                    self.reconnect_attempts = 0
                    backoff = self.initial_backoff_seconds

                    # Subscribe to logs mentions for Pump.fun and Raydium
                    sub_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "logsSubscribe",
                        "params": [
                            {"mentions": [PUMP_FUN_PROGRAM, RAYDIUM_AMM_PROGRAM]},
                            {"commitment": "confirmed"},
                        ],
                    }
                    await ws.send(json.dumps(sub_msg))

                    async for message in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(message)
                            params = data.get("params", {})
                            result = params.get("result", {})
                            value = result.get("value", {})
                            if value:
                                await self.handle_log_notification(value)
                        except Exception as e:
                            logger.debug("solana_listener.msg_parse_error", extra={"error": str(e)})
            except Exception as e:
                self.reconnect_attempts += 1
                logger.warning(
                    "solana_listener.connection_lost",
                    extra={
                        "attempt": self.reconnect_attempts,
                        "max": self.max_reconnect_attempts,
                        "error": str(e),
                    },
                )
                if self.reconnect_attempts >= self.max_reconnect_attempts:
                    logger.error("solana_listener.max_reconnect_reached")
                    break
                await asyncio.sleep(backoff)
                backoff *= self.backoff_multiplier

    def stop(self) -> None:
        self._running = False
