"""
ChronosX -- Circuit Breaker

Automatically halts trading when market conditions become dangerous:
  - Price moves too fast (volatility breaker)
  - Daily loss limit is breached (P&L breaker)
  - Order rejection rate is too high (risk breaker)

States:
    CLOSED  → trading allowed (normal)
    OPEN    → trading halted (breaker tripped)
    HALF    → one test order allowed (cooldown recovery)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional

from .types import PRICE_MULT


class BreakerState(IntEnum):
    CLOSED = 0
    OPEN   = 1
    HALF   = 2


@dataclass
class BreakerConfig:
    max_price_move_pct: float = 2.0
    window_sec:         float = 60.0
    max_loss_fixed:     int   = 500_000
    max_reject_rate:    float = 0.5
    reject_window:      int   = 20
    cooldown_sec:       float = 30.0


@dataclass
class BreakerEvent:
    reason:    str
    timestamp: float = field(default_factory=time.monotonic)
    price:     Optional[int] = None
    loss:      Optional[int] = None


class CircuitBreaker:
    """
    Guards order submission with configurable trip conditions.

    Usage:
        cb = CircuitBreaker(BreakerConfig(max_price_move_pct=1.5))
        cb.on_price(100_000)
        cb.on_price(102_000)
        if cb.allow():
            oms.submit(req)
    """

    def __init__(self, config: Optional[BreakerConfig] = None) -> None:
        self._cfg              = config or BreakerConfig()
        self._state            = BreakerState.CLOSED
        self._events:          List[BreakerEvent] = []
        self._tripped_at:      Optional[float] = None
        self._price_history:   List[tuple] = []
        self._recent_results:  List[bool] = []
        self._total_pnl:       int = 0

    @property
    def state(self) -> BreakerState:
        self._maybe_recover()
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == BreakerState.OPEN

    @property
    def is_closed(self) -> bool:
        return self.state == BreakerState.CLOSED

    @property
    def events(self) -> List[BreakerEvent]:
        return list(self._events)

    @property
    def trip_count(self) -> int:
        return len(self._events)

    def on_price(self, price: int) -> bool:
        now = time.monotonic()
        self._price_history.append((now, price))
        cutoff = now - self._cfg.window_sec
        self._price_history = [(t, p) for t, p in self._price_history if t >= cutoff]
        if len(self._price_history) < 2:
            return False
        oldest_price = self._price_history[0][1]
        if oldest_price == 0:
            return False
        move_pct = abs(price - oldest_price) / oldest_price * 100
        if move_pct > self._cfg.max_price_move_pct and self._state == BreakerState.CLOSED:
            self._trip(BreakerEvent(
                reason=f"Volatility: {move_pct:.2f}% move in {self._cfg.window_sec}s",
                price=price,
            ))
            return True
        return False

    def on_pnl_update(self, realised: int, unrealised: int) -> bool:
        self._total_pnl = realised + unrealised
        loss = -self._total_pnl
        if loss > self._cfg.max_loss_fixed and self._state == BreakerState.CLOSED:
            self._trip(BreakerEvent(
                reason=f"Loss limit: ${loss / PRICE_MULT:.2f} exceeded",
                loss=loss,
            ))
            return True
        return False

    def on_order_result(self, allowed: bool) -> bool:
        self._recent_results.append(allowed)
        if len(self._recent_results) > self._cfg.reject_window:
            self._recent_results.pop(0)
        if len(self._recent_results) < self._cfg.reject_window:
            return False
        reject_rate = self._recent_results.count(False) / len(self._recent_results)
        if reject_rate > self._cfg.max_reject_rate and self._state == BreakerState.CLOSED:
            self._trip(BreakerEvent(
                reason=f"Reject rate: {reject_rate:.1%} exceeded"
            ))
            return True
        return False

    def allow(self) -> bool:
        s = self.state
        if s == BreakerState.CLOSED:
            return True
        if s == BreakerState.HALF:
            self._state = BreakerState.OPEN
            return True
        return False

    def reset(self) -> None:
        self._state      = BreakerState.CLOSED
        self._tripped_at = None

    def _trip(self, event: BreakerEvent) -> None:
        self._state      = BreakerState.OPEN
        self._tripped_at = time.monotonic()
        self._events.append(event)

    def _maybe_recover(self) -> None:
        if (self._state == BreakerState.OPEN
                and self._tripped_at is not None
                and time.monotonic() - self._tripped_at >= self._cfg.cooldown_sec):
            self._state = BreakerState.HALF
