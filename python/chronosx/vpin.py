"""
ChronosX -- VPIN (Volume-synchronized Probability of Informed Trading)

Estimates how much order flow comes from informed traders.
High VPIN → informed trading → widen spreads / reduce size
Low VPIN  → noise trading   → tighten spreads / increase size
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List

from .types import Side, TradeEvent


@dataclass
class VpinBucket:
    buy_vol:  int
    sell_vol: int

    @property
    def total_vol(self) -> int:
        return self.buy_vol + self.sell_vol

    @property
    def imbalance(self) -> float:
        if self.total_vol == 0:
            return 0.0
        return abs(self.buy_vol - self.sell_vol) / self.total_vol


class VpinEstimator:
    """
    Computes rolling VPIN from a stream of trade events.

    Usage:
        vpin = VpinEstimator(bucket_size=500, window=10)
        vpin.on_trade(trade, Side.Buy)
        print(f"VPIN: {vpin.current:.3f}")
    """

    def __init__(self, bucket_size: int = 1000, window: int = 10) -> None:
        if bucket_size <= 0:
            raise ValueError("bucket_size must be positive")
        if window <= 0:
            raise ValueError("window must be positive")
        self._bucket_size = bucket_size
        self._window      = window
        self._cur_buy:    int = 0
        self._cur_sell:   int = 0
        self._buckets:    Deque[VpinBucket] = deque(maxlen=window)

    def on_trade(self, trade: TradeEvent, aggressor_side: Side) -> None:
        remaining = trade.qty
        while remaining > 0:
            space = self._bucket_size - (self._cur_buy + self._cur_sell)
            fill  = min(remaining, space)
            if aggressor_side == Side.Buy:
                self._cur_buy  += fill
            else:
                self._cur_sell += fill
            remaining -= fill
            if self._cur_buy + self._cur_sell >= self._bucket_size:
                self._close_bucket()

    def on_volume(self, qty: int, side: Side) -> None:
        dummy = TradeEvent(aggressor_id=0, resting_id=0, price=0, qty=qty)
        self.on_trade(dummy, side)

    @property
    def current(self) -> float:
        if not self._buckets:
            return 0.0
        return sum(b.imbalance for b in self._buckets) / len(self._buckets)

    @property
    def bucket_count(self) -> int:
        return len(self._buckets)

    @property
    def completed_buckets(self) -> List[VpinBucket]:
        return list(self._buckets)

    @property
    def toxicity_label(self) -> str:
        v = self.current
        if v >= 0.7:   return "HIGH"
        elif v >= 0.4: return "MEDIUM"
        return "LOW"

    def pending_volume(self) -> int:
        return self._cur_buy + self._cur_sell

    def __str__(self) -> str:
        return (f"VPIN={self.current:.3f} [{self.toxicity_label}] "
                f"buckets={self.bucket_count}/{self._window}")

    def _close_bucket(self) -> None:
        self._buckets.append(VpinBucket(
            buy_vol=self._cur_buy, sell_vol=self._cur_sell))
        self._cur_buy = self._cur_sell = 0
