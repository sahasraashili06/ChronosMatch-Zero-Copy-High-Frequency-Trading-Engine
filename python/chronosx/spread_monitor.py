"""
ChronosX -- Spread Monitor

Tracks bid-ask spread in real time and detects abnormal widening.
Useful for:
  - Detecting liquidity crises before they hit P&L
  - Auto-adjusting market-maker quoting width
  - Triggering circuit breakers on illiquid markets

Metrics:
  - Rolling mean and std (Welford online algorithm)
  - Z-score: how many std devs above normal is the current spread
  - Alert when z-score exceeds threshold
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from .types import PRICE_MULT
from .order_book import OrderBook


@dataclass
class SpreadAlert:
    """Fired when spread widens beyond threshold."""
    spread:       int    # current spread (fixed-point)
    mean:         float  # rolling mean
    z_score:      float  # standard deviations above mean
    sample_count: int


class SpreadMonitor:
    """
    Online spread tracker with z-score alerting.

    Usage:
        monitor = SpreadMonitor(z_threshold=3.0, min_samples=20)
        alert = monitor.update(book)
        if alert:
            print(f"Spread alert! z={alert.z_score:.1f}")
    """

    def __init__(self, z_threshold: float = 3.0, min_samples: int = 20) -> None:
        self._threshold   = z_threshold
        self._min_samples = min_samples
        self._count:  int   = 0
        self._mean:   float = 0.0
        self._M2:     float = 0.0
        self._current: Optional[int] = None
        self._alerts: List[SpreadAlert] = []

    def update(self, book: OrderBook) -> Optional[SpreadAlert]:
        spread = book.spread()
        if spread is None or spread <= 0:
            return None
        return self.update_raw(spread)

    def update_raw(self, spread: int) -> Optional[SpreadAlert]:
        if spread <= 0:
            return None
        self._current = spread
        self._welford(spread)
        if self._count < self._min_samples:
            return None
        z = self.z_score
        if z is not None and z > self._threshold:
            alert = SpreadAlert(spread=spread, mean=self._mean,
                                z_score=z, sample_count=self._count)
            self._alerts.append(alert)
            return alert
        return None

    @property
    def current_spread(self) -> Optional[int]:
        return self._current

    @property
    def current_spread_usd(self) -> float:
        return self._current / PRICE_MULT if self._current else 0.0

    @property
    def mean(self) -> float:
        return self._mean

    @property
    def mean_usd(self) -> float:
        return self._mean / PRICE_MULT

    @property
    def std(self) -> float:
        if self._count < 2:
            return 0.0
        return math.sqrt(self._M2 / (self._count - 1))

    @property
    def z_score(self) -> Optional[float]:
        if self._current is None or self.std == 0:
            return None
        return (self._current - self._mean) / self.std

    @property
    def sample_count(self) -> int:
        return self._count

    @property
    def alert_count(self) -> int:
        return len(self._alerts)

    @property
    def alerts(self) -> List[SpreadAlert]:
        return list(self._alerts)

    def is_wide(self) -> bool:
        z = self.z_score
        return z is not None and z > 2.0

    def reset(self) -> None:
        self._count = 0; self._mean = 0.0
        self._M2 = 0.0; self._current = None
        self._alerts.clear()

    def _welford(self, value: int) -> None:
        self._count += 1
        delta        = value - self._mean
        self._mean  += delta / self._count
        self._M2    += delta * (value - self._mean)
