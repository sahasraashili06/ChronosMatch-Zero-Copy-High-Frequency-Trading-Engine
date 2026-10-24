"""
ChronosX -- Circuit Breaker

Automatically halts trading when market conditions become dangerous:
  - Price moves too fast (volatility breaker)
  - Daily loss limit is breached (P&L breaker)
  - Order rejection rate is too high (risk breaker)

Used by exchanges and prop desks to prevent runaway losses.

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
    CLOSED = 0   # normal — trading allowed
    OPEN   = 1   # halted — trading blocked
    HALF   = 2   # cooldown — one probe allowed


@dataclass
class BreakerConfig:
    # Volatility: trip if price moves > max_price_move_pct % within window_sec
    max_price_move_pct: float = 2.0     # e.g. 2.0 = 2%
    window_sec:         float = 60.0    # rolling window

    # P&L: trip if realised + unrealised loss exceeds this (in fixed-point)
    max_loss_fixed:     int   = 500_000  # e.g. $50.00 at PRICE_MULT=10000

    # Rejection rate: trip if > max_reject_rate of recent orders are rejected
    max_reject_rate:    float = 0.5     # 50%
    reject_window:      int   = 20      # look at last N orders

    # Recovery: how long to stay OPEN before moving to HALF
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

        # Feed price updates
        cb.on_price(100_000)
        cb.on_price(102_000)   # may trip if > 1.5% move

        # Update P&L
        cb.on_pnl_update(realised=-300_000, unrealised=-250_000)

        # Check before submitting
        if cb.allow():
            oms.submit(req)
        else:
            print("Circuit breaker OPEN — order blocked")

        # After a trade goes through in HALF state
        cb.on_probe_success()
    """

    def __init__(self, config: Optional[BreakerConfig] = None) -> None:
        self._cfg       = config or BreakerConfig()
        self._state     = BreakerState.CLOSED
        self._events:   List[BreakerEvent] = []
        self._tripped_at: Optional[float]  = None

        # Volatility tracking
        self._price_history: List[tuple] = []   # (monotonic_ts, price)

        # Rejection rate tracking
        self._recent_results: List[bool] = []   # True=allowed, False=rejected

        # P&L
        self._total_pnl: int = 0

    # ── State ─────────────────────────────────────────────────────────────────

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

    # ── Inputs ────────────────────────────────────────────────────────────────

    def on_price(self, price: int) -> bool:
        """
        Feed a new price tick. Returns True if breaker was tripped.
        """
        now = time.monotonic()
        self._price_history.append((now, price))
        # Purge old entries outside window
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
        """
        Update total P&L. Returns True if loss limit was breached.
        """
        self._total_pnl = realised + unrealised
        loss = -self._total_pnl  # positive = loss

        if loss > self._cfg.max_loss_fixed and self._state == BreakerState.CLOSED:
            self._trip(BreakerEvent(
                reason=f"Loss limit: ${loss / PRICE_MULT:.2f} > "
                       f"${self._cfg.max_loss_fixed / PRICE_MULT:.2f}",
                loss=loss,
            ))
            return True
        return False

    def on_order_result(self, allowed: bool) -> bool:
        """
        Record whether an order was allowed or rejected.
        Returns True if rejection rate tripped the breaker.
        """
        self._recent_results.append(allowed)
        if len(self._recent_results) > self._cfg.reject_window:
            self._recent_results.pop(0)

        if len(self._recent_results) < self._cfg.reject_window:
            return False

        reject_rate = self._recent_results.count(False) / len(self._recent_results)
        if reject_rate > self._cfg.max_reject_rate and self._state == BreakerState.CLOSED:
            self._trip(BreakerEvent(
                reason=f"Reject rate: {reject_rate:.1%} > {self._cfg.max_reject_rate:.1%}"
            ))
            return True
        return False

    # ── Guard ─────────────────────────────────────────────────────────────────

    def allow(self) -> bool:
        """Returns True if an order may be submitted right now."""
        s = self.state
        if s == BreakerState.CLOSED:
            return True
        if s == BreakerState.HALF:
            # Allow exactly one probe then flip back to OPEN
            self._state = BreakerState.OPEN
            return True
        return False  # OPEN

    def reset(self) -> None:
        """Manually reset breaker to CLOSED (operator override)."""
        self._state      = BreakerState.CLOSED
        self._tripped_at = None

    def on_probe_success(self) -> None:
        """Call after a successful probe trade to fully close the breaker."""
        if self._state != BreakerState.OPEN:
            self._state      = BreakerState.CLOSED
            self._tripped_at = None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _trip(self, event: BreakerEvent) -> None:
        self._state      = BreakerState.OPEN
        self._tripped_at = time.monotonic()
        self._events.append(event)

    def _maybe_recover(self) -> None:
        """After cooldown_sec move from OPEN → HALF automatically."""
        if (self._state == BreakerState.OPEN
                and self._tripped_at is not None
                and time.monotonic() - self._tripped_at >= self._cfg.cooldown_sec):
            self._state = BreakerState.HALF
