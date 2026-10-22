"""
ChronosX -- Token Bucket Rate Limiter

Throttles order submission to comply with exchange rate limits.
Uses the classic token bucket algorithm:

  - Bucket refills at a fixed rate (tokens/second)
  - Each order consumes 1 token
  - If bucket is empty, the submit is blocked or rejected

Two modes:
  - Block mode  : wait until tokens refill (useful in simulation)
  - Reject mode : immediately reject when bucket is empty (production-like)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ThrottleStats:
    """Counters for rate limiter telemetry."""
    allowed:  int = 0
    rejected: int = 0
    waited_ns: int = 0   # total ns spent waiting (block mode)

    @property
    def total(self) -> int:
        return self.allowed + self.rejected

    @property
    def reject_rate(self) -> float:
        return self.rejected / self.total if self.total else 0.0

    def __str__(self) -> str:
        return (
            f"Throttle: allowed={self.allowed:,}  "
            f"rejected={self.rejected:,}  "
            f"reject_rate={self.reject_rate:.1%}  "
            f"waited={self.waited_ns/1e6:.1f}ms"
        )


class TokenBucket:
    """
    Token bucket rate limiter.

    Args:
        rate:     Tokens refilled per second.
        capacity: Maximum tokens the bucket can hold (burst size).
        block:    If True, consume() waits for tokens.
                  If False, consume() returns False immediately when empty.

    Usage:
        tb = TokenBucket(rate=1000, capacity=50)   # 1000 orders/sec, burst 50

        if tb.consume():
            oms.submit(req)
        else:
            print("rate limit hit — order rejected")

        print(tb.stats)
    """

    def __init__(
        self,
        rate:     float = 1000.0,
        capacity: float = 100.0,
        block:    bool  = False,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")

        self._rate      = rate
        self._capacity  = capacity
        self._block     = block
        self._tokens:   float = capacity     # start full
        self._last_ns:  int   = time.perf_counter_ns()
        self._stats     = ThrottleStats()

    # ── Public API ────────────────────────────────────────────────────────────

    def consume(self, tokens: float = 1.0) -> bool:
        """
        Try to consume *tokens* from the bucket.

        Returns True if successful (order may proceed),
        False if throttled (reject mode only).
        """
        self._refill()

        if self._tokens >= tokens:
            self._tokens -= tokens
            self._stats.allowed += 1
            return True

        if self._block:
            return self._wait_and_consume(tokens)

        self._stats.rejected += 1
        return False

    def available(self) -> float:
        """Current token count after refill."""
        self._refill()
        return self._tokens

    def reset(self) -> None:
        """Refill bucket to capacity and reset stats."""
        self._tokens  = self._capacity
        self._last_ns = time.perf_counter_ns()
        self._stats   = ThrottleStats()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def rate(self) -> float:
        return self._rate

    @property
    def capacity(self) -> float:
        return self._capacity

    @property
    def stats(self) -> ThrottleStats:
        return self._stats

    # ── Internal ──────────────────────────────────────────────────────────────

    def _refill(self) -> None:
        now_ns       = time.perf_counter_ns()
        elapsed_sec  = (now_ns - self._last_ns) / 1e9
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed_sec * self._rate,
        )
        self._last_ns = now_ns

    def _wait_and_consume(self, tokens: float) -> bool:
        """Block until enough tokens accumulate, then consume."""
        deficit    = tokens - self._tokens
        wait_sec   = deficit / self._rate
        wait_ns    = int(wait_sec * 1e9)
        t0         = time.perf_counter_ns()
        time.sleep(wait_sec)
        self._refill()
        self._tokens          -= tokens
        self._stats.allowed   += 1
        self._stats.waited_ns += time.perf_counter_ns() - t0
        return True


class MultiLevelThrottle:
    """
    Two-tier throttle: a per-second limit and a per-minute limit.
    Both buckets must have capacity for an order to proceed.

    Usage:
        mlt = MultiLevelThrottle(per_sec=100, per_min=3000)
        if mlt.consume():
            oms.submit(req)
    """

    def __init__(self, per_sec: float, per_min: float) -> None:
        self._second = TokenBucket(rate=per_sec, capacity=per_sec,  block=False)
        self._minute = TokenBucket(rate=per_min / 60, capacity=per_min, block=False)

    def consume(self) -> bool:
        if self._second.available() >= 1 and self._minute.available() >= 1:
            self._second.consume()
            self._minute.consume()
            return True
        return False

    @property
    def second_stats(self) -> ThrottleStats:
        return self._second.stats

    @property
    def minute_stats(self) -> ThrottleStats:
        return self._minute.stats
