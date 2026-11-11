"""
ChronosX -- Rolling Statistics

Generic online rolling window for any numeric signal.
No numpy required — pure Python using a deque.

Computes per tick:
  - Mean, Std (Welford), Min, Max
  - Z-score
  - Percentage change vs N bars ago

Used internally by SpreadMonitor and OFI, but exposed here as a
standalone utility that any signal can plug into.

Usage:
    rs = RollingStats(window=20)

    for price in prices:
        stat = rs.update(price)
        print(f"z={stat.z_score:.2f}  pct_chg={stat.pct_change:.2f}%")
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional


@dataclass
class StatSnapshot:
    value:      float
    mean:       float
    std:        float
    min_val:    float
    max_val:    float
    z_score:    Optional[float]
    pct_change: Optional[float]   # vs oldest value in window
    count:      int

    @property
    def is_above_mean(self) -> bool:
        return self.value > self.mean

    @property
    def is_extreme(self, threshold: float = 2.0) -> bool:
        z = self.z_score
        return z is not None and abs(z) > threshold

    def __str__(self) -> str:
        z = f"{self.z_score:.2f}" if self.z_score is not None else "n/a"
        p = f"{self.pct_change:+.2f}%" if self.pct_change is not None else "n/a"
        return (
            f"Stats[n={self.count}]  "
            f"val={self.value:.4f}  mean={self.mean:.4f}  "
            f"std={self.std:.4f}  z={z}  chg={p}"
        )


class RollingStats:
    """
    Online rolling-window statistics using Welford's algorithm.

    Args:
        window : number of samples in the rolling window.
    """

    def __init__(self, window: int = 20) -> None:
        if window < 2:
            raise ValueError("window must be >= 2")
        self._window  = window
        self._buf:    Deque[float] = deque(maxlen=window)
        self._count:  int   = 0
        self._mean:   float = 0.0
        self._M2:     float = 0.0  # Welford's sum of squared deviations
        self._min:    float = float("inf")
        self._max:    float = float("-inf")

    # ── Feed ──────────────────────────────────────────────────────────────────

    def update(self, value: float) -> StatSnapshot:
        """Add a new value and return a StatSnapshot."""
        # Evict oldest if window full (Welford correction on removal)
        if len(self._buf) == self._window:
            old = self._buf[0]
            old_mean    = self._mean
            self._count -= 1
            if self._count > 0:
                self._mean -= (old - self._mean) / self._count
                self._M2   -= (old - old_mean) * (old - self._mean)
                self._M2    = max(0.0, self._M2)
            else:
                self._mean = 0.0
                self._M2   = 0.0

        # Insert new value (Welford)
        self._buf.append(value)
        self._count += 1
        delta        = value - self._mean
        self._mean  += delta / self._count
        delta2       = value - self._mean
        self._M2    += delta * delta2

        # Min / Max over current window
        self._min = min(self._buf)
        self._max = max(self._buf)

        std    = math.sqrt(self._M2 / (self._count - 1)) if self._count >= 2 else 0.0
        z      = (value - self._mean) / std if std > 0 else None
        oldest = self._buf[0] if len(self._buf) > 1 else None
        pct    = ((value - oldest) / oldest * 100) if oldest and oldest != 0 else None

        return StatSnapshot(
            value=value, mean=self._mean, std=std,
            min_val=self._min, max_val=self._max,
            z_score=z, pct_change=pct, count=self._count,
        )

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def mean(self) -> float:
        return self._mean

    @property
    def std(self) -> float:
        return math.sqrt(self._M2 / (self._count - 1)) if self._count >= 2 else 0.0

    @property
    def sample_count(self) -> int:
        return self._count

    @property
    def is_full(self) -> bool:
        return len(self._buf) == self._window

    def reset(self) -> None:
        self._buf.clear()
        self._count = 0
        self._mean  = 0.0
        self._M2    = 0.0
        self._min   = float("inf")
        self._max   = float("-inf")
