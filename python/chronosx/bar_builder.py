"""
ChronosX -- OHLCV Bar Builder

Aggregates raw trade ticks into OHLCV (Open/High/Low/Close/Volume) bars.

Supports three bar types:
  - Time bars  : fixed time interval (e.g. 1s, 1min)
  - Tick bars  : fixed number of trades per bar
  - Volume bars: fixed volume per bar (favoured in HFT research)

All prices stored as fixed-point integers (× PRICE_MULT).

Usage:
    builder = BarBuilder(bar_type=BarType.Volume, size=1000)

    for trade in trades:
        bar = builder.on_trade(trade)
        if bar:                        # bar just closed
            print(bar)

    partial = builder.current_bar     # incomplete bar in progress
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional

from .types import TradeEvent, PRICE_MULT


class BarType(IntEnum):
    Time   = 0   # fixed seconds
    Tick   = 1   # fixed trade count
    Volume = 2   # fixed cumulative volume


@dataclass
class OhlcvBar:
    """One completed OHLCV bar."""
    bar_type:  BarType
    open:      int     # fixed-point
    high:      int
    low:       int
    close:     int
    volume:    int
    tick_count: int
    open_ts:   float   # monotonic timestamp when bar opened
    close_ts:  float

    @property
    def open_usd(self)  -> float: return self.open  / PRICE_MULT
    @property
    def high_usd(self)  -> float: return self.high  / PRICE_MULT
    @property
    def low_usd(self)   -> float: return self.low   / PRICE_MULT
    @property
    def close_usd(self) -> float: return self.close / PRICE_MULT
    @property
    def vwap(self)      -> float:
        return self._notional / (self.volume * PRICE_MULT) if self.volume else 0.0

    # internal — set by builder
    _notional: int = field(default=0, repr=False)

    @property
    def range(self) -> int:
        return self.high - self.low

    @property
    def duration_sec(self) -> float:
        return self.close_ts - self.open_ts

    def __str__(self) -> str:
        return (
            f"Bar[{self.bar_type.name}] "
            f"O={self.open_usd:.4f} H={self.high_usd:.4f} "
            f"L={self.low_usd:.4f} C={self.close_usd:.4f} "
            f"V={self.volume:,} ticks={self.tick_count} "
            f"VWAP={self.vwap:.4f}"
        )


class BarBuilder:
    """
    Builds OHLCV bars from a stream of TradeEvents.

    Args:
        bar_type : Time, Tick, or Volume
        size     : seconds (Time), trades (Tick), or units (Volume)

    Returns a completed OhlcvBar from on_trade() when a bar closes,
    else returns None.
    """

    def __init__(self, bar_type: BarType = BarType.Volume, size: int = 1000) -> None:
        if size <= 0:
            raise ValueError("size must be positive")
        self._type      = bar_type
        self._size      = size
        self._bars:     List[OhlcvBar] = []
        self._reset()

    # ── Feed ──────────────────────────────────────────────────────────────────

    def on_trade(self, trade: TradeEvent) -> Optional[OhlcvBar]:
        """
        Process one trade. Returns a closed OhlcvBar if one completed,
        else returns None.
        """
        price = trade.price
        qty   = trade.qty
        now   = time.monotonic()

        # Open the bar on first trade
        if self._open is None:
            self._open    = price
            self._open_ts = now

        # Update OHLC
        self._high     = max(self._high, price)
        self._low      = min(self._low, price)
        self._close    = price
        self._volume   += qty
        self._ticks    += 1
        self._notional += price * qty

        # Check if bar should close
        should_close = False
        if self._type == BarType.Tick:
            should_close = self._ticks >= self._size
        elif self._type == BarType.Volume:
            should_close = self._volume >= self._size
        elif self._type == BarType.Time:
            should_close = (now - self._open_ts) >= self._size

        if should_close:
            return self._close_bar(now)
        return None

    def flush(self) -> Optional[OhlcvBar]:
        """Force-close the current partial bar (e.g. at session end)."""
        if self._open is None:
            return None
        return self._close_bar(time.monotonic())

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def current_bar(self) -> Optional[dict]:
        """Snapshot of the in-progress bar (not yet closed)."""
        if self._open is None:
            return None
        return {
            "open": self._open, "high": self._high,
            "low":  self._low,  "close": self._close,
            "volume": self._volume, "ticks": self._ticks,
        }

    @property
    def completed_bars(self) -> List[OhlcvBar]:
        return list(self._bars)

    @property
    def bar_count(self) -> int:
        return len(self._bars)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _close_bar(self, now: float) -> OhlcvBar:
        bar = OhlcvBar(
            bar_type   = self._type,
            open       = self._open,       # type: ignore[arg-type]
            high       = self._high,
            low        = self._low,
            close      = self._close,
            volume     = self._volume,
            tick_count = self._ticks,
            open_ts    = self._open_ts,
            close_ts   = now,
            _notional  = self._notional,
        )
        self._bars.append(bar)
        self._reset()
        return bar

    def _reset(self) -> None:
        self._open:     Optional[int] = None
        self._high:     int = 0
        self._low:      int = 2**62
        self._close:    int = 0
        self._volume:   int = 0
        self._ticks:    int = 0
        self._notional: int = 0
        self._open_ts:  float = 0.0
