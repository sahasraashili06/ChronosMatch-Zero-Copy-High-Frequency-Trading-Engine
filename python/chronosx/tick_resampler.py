"""
ChronosX -- Tick Resampler

Converts a raw stream of price ticks into fixed-interval OHLCV bars
without buffering all ticks in memory. Each interval produces one bar
the moment it closes, making it suitable for real-time pipelines.

Differs from BarBuilder (which uses tick/volume thresholds) —
this module strictly uses wall-clock time intervals.

Usage:
    rs = TickResampler(interval_sec=1.0)

    for price, qty, ts in tick_feed:
        bar = rs.on_tick(price=price, qty=qty, timestamp=ts)
        if bar:
            strategy.on_bar(bar)   # bar just closed
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from .types import PRICE_MULT


@dataclass
class ResampledBar:
    interval_sec: float
    open:   int      # fixed-point
    high:   int
    low:    int
    close:  int
    volume: int
    tick_count: int
    ts_open:  float  # start of interval (seconds)
    ts_close: float  # end of interval

    @property
    def open_usd(self)  -> float: return self.open  / PRICE_MULT
    @property
    def high_usd(self)  -> float: return self.high  / PRICE_MULT
    @property
    def low_usd(self)   -> float: return self.low   / PRICE_MULT
    @property
    def close_usd(self) -> float: return self.close / PRICE_MULT

    @property
    def vwap(self) -> float:
        return self._notional / (self.volume * PRICE_MULT) if self.volume else 0.0

    _notional: int = 0   # set by resampler

    @property
    def range_usd(self) -> float:
        return (self.high - self.low) / PRICE_MULT

    def __str__(self) -> str:
        return (
            f"Bar[{self.interval_sec}s]  "
            f"O={self.open_usd:.4f}  H={self.high_usd:.4f}  "
            f"L={self.low_usd:.4f}  C={self.close_usd:.4f}  "
            f"V={self.volume}  ticks={self.tick_count}"
        )


class TickResampler:
    """
    Resamples a raw tick stream into fixed-time OHLCV bars.

    Args:
        interval_sec : bar width in seconds (e.g. 1.0, 60.0, 300.0).

    Call on_tick() for every incoming trade.
    Returns a completed ResampledBar when the interval closes, else None.
    """

    def __init__(self, interval_sec: float = 1.0) -> None:
        if interval_sec <= 0:
            raise ValueError("interval_sec must be positive")
        self._interval    = interval_sec
        self._bars:       List[ResampledBar] = []
        self._bar_start:  Optional[float] = None
        self._open:       int = 0
        self._high:       int = 0
        self._low:        int = 0
        self._close:      int = 0
        self._volume:     int = 0
        self._ticks:      int = 0
        self._notional:   int = 0

    def on_tick(
        self,
        price:     int,
        qty:       int = 1,
        timestamp: Optional[float] = None,
    ) -> Optional[ResampledBar]:
        """
        Process one tick.

        Args:
            price     : fixed-point trade price.
            qty       : trade quantity (default 1).
            timestamp : epoch seconds. If None, uses internal counter
                        (monotonically incrementing by interval each call).
        """
        if timestamp is None:
            timestamp = (self._ticks_total if hasattr(self, "_ticks_total")
                         else 0.0)
            if not hasattr(self, "_ticks_total"):
                self._ticks_total = 0.0
            self._ticks_total += self._interval / 10   # synthetic timestamps

        closed_bar: Optional[ResampledBar] = None

        # First tick ever
        if self._bar_start is None:
            self._bar_start = self._floor(timestamp)
            self._open_bar(price)

        # Check if this tick falls into a new interval
        elif timestamp >= self._bar_start + self._interval:
            closed_bar  = self._close_bar()
            self._bar_start = self._floor(timestamp)
            self._open_bar(price)

        # Update current bar
        self._high      = max(self._high, price)
        self._low       = min(self._low, price)
        self._close     = price
        self._volume   += qty
        self._ticks    += 1
        self._notional += price * qty

        return closed_bar

    def flush(self) -> Optional[ResampledBar]:
        """Force-close the current partial bar (e.g. at session end)."""
        if self._bar_start is None or self._ticks == 0:
            return None
        bar = self._close_bar()
        self._bar_start = None   # mark as flushed — next tick opens a new bar
        return bar

    @property
    def completed_bars(self) -> List[ResampledBar]:
        return list(self._bars)

    @property
    def bar_count(self) -> int:
        return len(self._bars)

    @property
    def current(self) -> Optional[dict]:
        if self._bar_start is None:
            return None
        return {
            "open": self._open, "high": self._high, "low": self._low,
            "close": self._close, "volume": self._volume, "ticks": self._ticks,
        }

    def reset(self) -> None:
        self._bars.clear()
        self._bar_start = None
        self._ticks = self._volume = self._notional = 0
        if hasattr(self, "_ticks_total"):
            self._ticks_total = 0.0

    def _floor(self, ts: float) -> float:
        """Snap timestamp to interval boundary."""
        return math.floor(ts / self._interval) * self._interval

    def _open_bar(self, price: int) -> None:
        self._open = price
        self._high = price
        self._low  = price
        self._close = price
        self._volume = self._ticks = self._notional = 0

    def _close_bar(self) -> ResampledBar:
        bar = ResampledBar(
            interval_sec = self._interval,
            open    = self._open,
            high    = self._high,
            low     = self._low,
            close   = self._close,
            volume  = self._volume,
            tick_count = self._ticks,
            ts_open  = self._bar_start,            # type: ignore[arg-type]
            ts_close = self._bar_start + self._interval,
            _notional = self._notional,
        )
        self._bars.append(bar)
        return bar
