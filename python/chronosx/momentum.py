"""
ChronosX -- Momentum Signal

Computes short-term price momentum signals used in HFT alpha research:

  1. Price Return   : (current - n_bars_ago) / n_bars_ago
  2. EMA Crossover  : fast EMA crosses above/below slow EMA
  3. RSI            : Relative Strength Index

All inputs are fixed-point prices (× PRICE_MULT).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Deque, Optional
from collections import deque

from .types import PRICE_MULT


class Signal(IntEnum):
    SELL    = -1
    NEUTRAL =  0
    BUY     =  1


@dataclass
class MomentumReading:
    price:       int
    return_pct:  float
    fast_ema:    float
    slow_ema:    float
    rsi:         float
    signal:      Signal

    @property
    def ema_spread(self) -> float:
        return self.fast_ema - self.slow_ema

    @property
    def is_overbought(self) -> bool:
        return self.rsi > 70

    @property
    def is_oversold(self) -> bool:
        return self.rsi < 30

    def __str__(self) -> str:
        return (
            f"Momentum: signal={self.signal.name:7s}  "
            f"ret={self.return_pct:+.3f}%  "
            f"EMA({self.fast_ema/PRICE_MULT:.4f}/{self.slow_ema/PRICE_MULT:.4f})  "
            f"RSI={self.rsi:.1f}"
        )


class MomentumSignal:
    """
    Combines return, EMA crossover, and RSI into a directional signal.

    Args:
        fast:       Fast EMA period.
        slow:       Slow EMA period.
        rsi_period: RSI lookback period.
        lookback:   Bars back for return computation.

    Usage:
        sig = MomentumSignal(fast=5, slow=20)
        for price in prices:
            r = sig.update(price)
            if r.signal == Signal.BUY:
                print("BUY")
    """

    def __init__(self, fast=5, slow=20, rsi_period=14, lookback=10):
        if fast >= slow:
            raise ValueError("fast must be less than slow")
        self._fast_k   = 2 / (fast + 1)
        self._slow_k   = 2 / (slow + 1)
        self._rsi_k    = 2 / (rsi_period + 1)
        self._lookback = lookback
        self._fast_ema: Optional[float] = None
        self._slow_ema: Optional[float] = None
        self._avg_gain: Optional[float] = None
        self._avg_loss: Optional[float] = None
        self._prices:   Deque[int] = deque(maxlen=lookback + 1)
        self._prev:     Optional[int] = None
        self._count:    int = 0

    def update(self, price: int) -> MomentumReading:
        self._prices.append(price)
        self._count += 1

        if self._fast_ema is None:
            self._fast_ema = float(price)
            self._slow_ema = float(price)
        else:
            self._fast_ema = price * self._fast_k + self._fast_ema * (1 - self._fast_k)
            self._slow_ema = price * self._slow_k + self._slow_ema * (1 - self._slow_k)

        rsi = 50.0
        if self._prev is not None:
            delta = price - self._prev
            gain, loss = max(0.0, float(delta)), max(0.0, float(-delta))
            if self._avg_gain is None:
                self._avg_gain, self._avg_loss = gain, loss
            else:
                self._avg_gain = gain * self._rsi_k + self._avg_gain * (1 - self._rsi_k)
                self._avg_loss = loss * self._rsi_k + self._avg_loss * (1 - self._rsi_k)
            if self._avg_loss and self._avg_loss > 0:
                rsi = 100 - 100 / (1 + self._avg_gain / self._avg_loss)
            elif self._avg_gain and self._avg_gain > 0:
                rsi = 100.0
        self._prev = price

        ret = 0.0
        if len(self._prices) == self._lookback + 1 and self._prices[0] > 0:
            ret = (price - self._prices[0]) / self._prices[0] * 100

        ema_bull = self._fast_ema > self._slow_ema
        if ema_bull and ret > 0 and rsi < 70:
            signal = Signal.BUY
        elif not ema_bull and ret < 0 and rsi > 30:
            signal = Signal.SELL
        else:
            signal = Signal.NEUTRAL

        return MomentumReading(
            price=price, return_pct=ret,
            fast_ema=self._fast_ema, slow_ema=self._slow_ema,
            rsi=rsi, signal=signal,
        )

    @property
    def sample_count(self) -> int:
        return self._count

    @property
    def fast_ema(self) -> Optional[float]:
        return self._fast_ema

    @property
    def slow_ema(self) -> Optional[float]:
        return self._slow_ema

    def reset(self) -> None:
        self._fast_ema = self._slow_ema = None
        self._avg_gain = self._avg_loss = None
        self._prev = None
        self._prices.clear()
        self._count = 0
