"""
ChronosX -- Trade Throttler

Rate-limits order submission to protect against runaway strategies,
fat-finger errors, and exchange throttle rejections.

Enforces:
  1. Max orders per second  (token-bucket algorithm)
  2. Max notional per minute (rolling window sum)
  3. Max consecutive rejects before cooldown

Token bucket:
  - Refills at `rate` tokens/second continuously
  - Burst up to `capacity` tokens
  - Each order consumes 1 token

Usage:
    throttle = TradeThrottler(rate=100, capacity=10, max_notional=1_000_000)

    if throttle.allow(order_notional=50_000):
        exchange.send(order)
    else:
        print(f"Throttled: {throttle.reject_reason}")
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional


@dataclass
class ThrottleStatus:
    allowed:       bool
    tokens_left:   float
    notional_used: int     # fixed-point, last 60s
    reject_reason: Optional[str] = None


class TradeThrottler:
    """
    Token-bucket rate limiter with notional cap.

    Args:
        rate            : tokens refilled per second.
        capacity        : max burst tokens.
        max_notional    : max notional (fixed-point) per rolling 60s window.
        max_consec_rej  : halt after this many consecutive rejects.
        cooldown_sec    : seconds to wait after hitting consec_rej limit.
    """

    def __init__(
        self,
        rate:           float = 100.0,
        capacity:       float = 10.0,
        max_notional:   int   = 0,         # 0 = disabled
        max_consec_rej: int   = 5,
        cooldown_sec:   float = 10.0,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")

        self._rate          = rate
        self._capacity      = capacity
        self._tokens        = float(capacity)
        self._last_refill   = time.monotonic()

        self._max_notional  = max_notional
        self._notional_win: Deque[tuple] = deque()  # (timestamp, notional)

        self._max_consec    = max_consec_rej
        self._consec_rej    = 0
        self._cooldown_sec  = cooldown_sec
        self._cooldown_until: float = 0.0

        self._total_allowed = 0
        self._total_rejected = 0

    # ── Main API ──────────────────────────────────────────────────────────────

    def allow(self, order_notional: int = 0) -> bool:
        """
        Check whether an order is allowed right now.
        Consumes one token and records the notional if allowed.
        Returns True if the order may proceed.
        """
        now = self._refill()
        reason = self._check(now, order_notional)

        if reason is None:
            self._tokens       -= 1
            self._consec_rej    = 0
            self._total_allowed += 1
            if order_notional > 0:
                self._notional_win.append((now, order_notional))
            return True
        else:
            self._consec_rej += 1
            self._total_rejected += 1
            if self._consec_rej >= self._max_consec:
                self._cooldown_until = now + self._cooldown_sec
            self._last_reason = reason
            return False

    def status(self) -> ThrottleStatus:
        now = self._refill()
        used = self._notional_used(now)
        return ThrottleStatus(
            allowed       = self._check(now, 0) is None,
            tokens_left   = self._tokens,
            notional_used = used,
            reject_reason = getattr(self, "_last_reason", None),
        )

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def reject_reason(self) -> Optional[str]:
        return getattr(self, "_last_reason", None)

    @property
    def total_allowed(self) -> int:
        return self._total_allowed

    @property
    def total_rejected(self) -> int:
        return self._total_rejected

    @property
    def tokens(self) -> float:
        self._refill()
        return self._tokens

    def is_cooling_down(self) -> bool:
        return time.monotonic() < self._cooldown_until

    def reset(self) -> None:
        self._tokens        = self._capacity
        self._last_refill   = time.monotonic()
        self._notional_win.clear()
        self._consec_rej    = 0
        self._cooldown_until = 0.0
        self._total_allowed  = 0
        self._total_rejected = 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _refill(self) -> float:
        now     = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now
        return now

    def _check(self, now: float, notional: int) -> Optional[str]:
        if now < self._cooldown_until:
            return f"Cooldown active ({self._cooldown_until - now:.1f}s left)"
        if self._tokens < 1.0:
            return f"Rate limit: {self._tokens:.2f} tokens left"
        if self._max_notional > 0:
            used = self._notional_used(now)
            if used + notional > self._max_notional:
                return f"Notional cap: {used}/{self._max_notional} used"
        return None

    def _notional_used(self, now: float) -> int:
        cutoff = now - 60.0
        while self._notional_win and self._notional_win[0][0] < cutoff:
            self._notional_win.popleft()
        return sum(n for _, n in self._notional_win)
