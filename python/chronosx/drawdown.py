"""
ChronosX -- Drawdown Tracker

Real-time peak-to-trough monitoring for live P&L.

Tracks:
  - Running peak equity
  - Current drawdown (absolute + percentage)
  - Maximum drawdown seen (absolute + percentage)
  - Drawdown duration (how many updates since the peak)

Used by the circuit breaker and risk manager to halt trading
before losses become catastrophic.

Usage:
    dd = DrawdownTracker(initial_equity=100_000.0)
    dd.update(99_000)
    dd.update(97_500)

    print(dd.current_pct)     # -2.5
    print(dd.max_drawdown_pct) # -2.5
    print(dd.is_in_drawdown)  # True
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DrawdownEvent:
    """Snapshot of a drawdown recorded when a new max is set."""
    equity:    float
    peak:      float
    drawdown:  float   # negative number, absolute USD
    pct:       float   # negative %, e.g. -5.0
    duration:  int     # bars since peak


class DrawdownTracker:
    """
    Tracks peak-to-trough equity drawdown in real time.

    Args:
        initial_equity: Starting equity value (USD).
        alert_pct:      If drawdown exceeds this %, record an alert event.
                        E.g. 5.0 means alert when equity drops >5% from peak.
    """

    def __init__(self, initial_equity: float = 0.0, alert_pct: float = 5.0) -> None:
        if alert_pct <= 0:
            raise ValueError("alert_pct must be positive")
        self._alert_pct      = alert_pct
        self._peak:      float = initial_equity
        self._equity:    float = initial_equity
        self._max_dd:    float = 0.0        # worst absolute drawdown (negative)
        self._max_dd_pct: float = 0.0       # worst % drawdown (negative)
        self._duration:  int   = 0          # bars since last peak
        self._count:     int   = 0
        self._alerts:    List[DrawdownEvent] = []

    # ── Feed ──────────────────────────────────────────────────────────────────

    def update(self, equity: float) -> Optional[DrawdownEvent]:
        """
        Feed current equity. Returns a DrawdownEvent if a new max drawdown
        alert threshold is breached, else None.
        """
        self._equity = equity
        self._count += 1

        if equity >= self._peak:
            self._peak     = equity
            self._duration = 0
            return None

        self._duration += 1
        dd     = equity - self._peak          # negative
        dd_pct = dd / self._peak * 100 if self._peak else 0.0

        if dd < self._max_dd:
            self._max_dd     = dd
            self._max_dd_pct = dd_pct

        if abs(dd_pct) >= self._alert_pct:
            event = DrawdownEvent(
                equity=equity, peak=self._peak,
                drawdown=dd, pct=dd_pct, duration=self._duration,
            )
            # Only append if this is a new worst alert
            if not self._alerts or dd < self._alerts[-1].drawdown:
                self._alerts.append(event)
            return event
        return None

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def current_drawdown(self) -> float:
        """Absolute drawdown from peak (negative or 0)."""
        dd = self._equity - self._peak
        return min(dd, 0.0)

    @property
    def current_pct(self) -> float:
        """Drawdown as a percentage from peak (negative or 0)."""
        if self._peak == 0:
            return 0.0
        return self.current_drawdown / self._peak * 100

    @property
    def max_drawdown(self) -> float:
        """Worst absolute drawdown seen (negative or 0)."""
        return self._max_dd

    @property
    def max_drawdown_pct(self) -> float:
        """Worst percentage drawdown seen (negative or 0)."""
        return self._max_dd_pct

    @property
    def peak(self) -> float:
        return self._peak

    @property
    def equity(self) -> float:
        return self._equity

    @property
    def duration(self) -> int:
        """Number of updates since the last equity peak."""
        return self._duration

    @property
    def is_in_drawdown(self) -> bool:
        return self._equity < self._peak

    @property
    def alert_count(self) -> int:
        return len(self._alerts)

    @property
    def alerts(self) -> List[DrawdownEvent]:
        return list(self._alerts)

    @property
    def sample_count(self) -> int:
        return self._count

    def reset(self, new_equity: Optional[float] = None) -> None:
        eq = new_equity if new_equity is not None else self._equity
        self._peak       = eq
        self._equity     = eq
        self._max_dd     = 0.0
        self._max_dd_pct = 0.0
        self._duration   = 0
        self._count      = 0
        self._alerts.clear()

    def __str__(self) -> str:
        return (
            f"DrawdownTracker  equity=${self._equity:,.2f}  "
            f"peak=${self._peak:,.2f}  "
            f"current={self.current_pct:.2f}%  "
            f"max={self.max_drawdown_pct:.2f}%  "
            f"dur={self._duration}"
        )
