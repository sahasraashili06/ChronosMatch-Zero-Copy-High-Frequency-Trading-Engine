"""
ChronosX -- Order Flow Imbalance (OFI)

Measures buy-side vs sell-side pressure from order book updates.
OFI is one of the strongest short-term price predictors in HFT research
(Cont et al. 2013, "The Price Impact of Order Book Events").

OFI = sum of (bid size changes - ask size changes) over a window.
  - Positive OFI → buy pressure → price likely to rise
  - Negative OFI → sell pressure → price likely to fall

Variants tracked:
  - Raw OFI     : signed volume imbalance per tick
  - Normalised  : OFI / total volume (bounded [-1, +1])
  - Rolling sum : over configurable window

Usage:
    ofi = OFICalculator(window=20)

    # Feed on every order book update
    ofi.update(
        bid_price=100_050, bid_qty=500,
        ask_price=100_100, ask_qty=300,
    )

    print(f"OFI: {ofi.current:.3f}")
    print(f"Signal: {ofi.signal}")   # BUY / SELL / NEUTRAL
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from typing import Deque, Optional


class OFISignal(IntEnum):
    SELL    = -1
    NEUTRAL =  0
    BUY     =  1


@dataclass
class OFISnapshot:
    raw:        int    # signed volume imbalance this tick
    normalised: float  # raw / total volume, bounded [-1, +1]
    rolling:    float  # rolling-window OFI
    signal:     OFISignal


class OFICalculator:
    """
    Tracks Order Flow Imbalance from best bid/ask size changes.

    Args:
        window        : number of ticks for the rolling sum.
        signal_thresh : normalised OFI threshold to emit BUY/SELL.
    """

    def __init__(self, window: int = 20, signal_thresh: float = 0.2) -> None:
        if window < 1:
            raise ValueError("window must be >= 1")
        if not (0 < signal_thresh < 1):
            raise ValueError("signal_thresh must be in (0, 1)")

        self._window     = window
        self._thresh     = signal_thresh
        self._history:   Deque[int] = deque(maxlen=window)

        # Previous book state
        self._prev_bid_price: Optional[int] = None
        self._prev_bid_qty:   Optional[int] = None
        self._prev_ask_price: Optional[int] = None
        self._prev_ask_qty:   Optional[int] = None

        self._last: Optional[OFISnapshot] = None
        self._count: int = 0

    # ── Feed ──────────────────────────────────────────────────────────────────

    def update(
        self,
        bid_price: int,
        bid_qty:   int,
        ask_price: int,
        ask_qty:   int,
    ) -> OFISnapshot:
        """
        Feed a new best-bid/ask snapshot.
        Returns an OFISnapshot with the current imbalance reading.
        """
        self._count += 1

        # Compute bid-side contribution
        if self._prev_bid_price is None:
            bid_contrib = bid_qty
        elif bid_price > self._prev_bid_price:
            bid_contrib = bid_qty                    # new higher bid → full size
        elif bid_price == self._prev_bid_price:
            bid_contrib = bid_qty - self._prev_bid_qty  # same level, size delta
        else:
            bid_contrib = -self._prev_bid_qty        # bid fell away → negative

        # Compute ask-side contribution
        if self._prev_ask_price is None:
            ask_contrib = ask_qty
        elif ask_price < self._prev_ask_price:
            ask_contrib = ask_qty                    # new lower ask → full size
        elif ask_price == self._prev_ask_price:
            ask_contrib = ask_qty - self._prev_ask_qty
        else:
            ask_contrib = -self._prev_ask_qty        # ask rose away → negative

        raw = bid_contrib - ask_contrib
        self._history.append(raw)

        total = abs(bid_contrib) + abs(ask_contrib)
        norm  = raw / total if total > 0 else 0.0
        norm  = max(-1.0, min(1.0, norm))

        rolling = sum(self._history) / len(self._history) if self._history else 0.0

        if norm > self._thresh:
            signal = OFISignal.BUY
        elif norm < -self._thresh:
            signal = OFISignal.SELL
        else:
            signal = OFISignal.NEUTRAL

        # Store state
        self._prev_bid_price = bid_price
        self._prev_bid_qty   = bid_qty
        self._prev_ask_price = ask_price
        self._prev_ask_qty   = ask_qty

        snap = OFISnapshot(raw=raw, normalised=norm, rolling=rolling, signal=signal)
        self._last = snap
        return snap

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def current(self) -> float:
        """Most recent normalised OFI value."""
        return self._last.normalised if self._last else 0.0

    @property
    def rolling(self) -> float:
        """Rolling average of raw OFI over the window."""
        return self._last.rolling if self._last else 0.0

    @property
    def signal(self) -> OFISignal:
        return self._last.signal if self._last else OFISignal.NEUTRAL

    @property
    def sample_count(self) -> int:
        return self._count

    def reset(self) -> None:
        self._history.clear()
        self._prev_bid_price = self._prev_bid_qty = None
        self._prev_ask_price = self._prev_ask_qty = None
        self._last  = None
        self._count = 0

    def __str__(self) -> str:
        return (
            f"OFI  normalised={self.current:+.3f}  "
            f"rolling={self.rolling:+.1f}  "
            f"signal={self.signal.name}"
        )
