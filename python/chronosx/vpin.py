"""
ChronosX -- Order Flow Toxicity (VPIN)

Volume-synchronized Probability of Informed Trading (VPIN).

VPIN estimates how much of the order flow comes from informed traders
(people who KNOW something) vs noise traders. It is widely used in HFT
as a leading indicator of adverse selection and liquidity crises.

    VPIN = |V_buy - V_sell| / V_total   (per volume bucket)

High VPIN (> 0.7) → informed trading likely → widen spreads / reduce size
Low VPIN  (< 0.3) → mostly noise → tighten spreads / increase size

Reference: Easley, Lopez de Prado, O'Hara (2012)
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional

from .types import Side, TradeEvent


@dataclass
class VpinBucket:
    """One completed volume bucket."""
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

    Args:
        bucket_size: Volume per bucket (e.g. 1000 shares).
        window:      Number of completed buckets to average over.

    Usage:
        vpin = VpinEstimator(bucket_size=500, window=10)

        for trade in trades:
            vpin.on_trade(trade)

        print(f"VPIN: {vpin.current:.3f}")   # 0.0 – 1.0
        if vpin.current > 0.7:
            print("HIGH toxicity — widen spreads!")
    """

    def __init__(self, bucket_size: int = 1000, window: int = 10) -> None:
        if bucket_size <= 0:
            raise ValueError("bucket_size must be positive")
        if window <= 0:
            raise ValueError("window must be positive")

        self._bucket_size = bucket_size
        self._window      = window

        # Current incomplete bucket
        self._cur_buy:  int = 0
        self._cur_sell: int = 0

        # Completed buckets (rolling)
        self._buckets: Deque[VpinBucket] = deque(maxlen=window)

    # ── Feed ──────────────────────────────────────────────────────────────────

    def on_trade(self, trade: TradeEvent, aggressor_side: Side) -> None:
        """Feed one trade. Automatically closes buckets when full."""
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
        """Feed raw volume directly (without a TradeEvent object)."""
        from .types import TradeEvent as _TE
        dummy = _TE(aggressor_id=0, resting_id=0, price=0, qty=qty)
        self.on_trade(dummy, side)

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def current(self) -> float:
        """Rolling VPIN over last *window* buckets. Returns 0.0 if no data."""
        if not self._buckets:
            return 0.0
        total_imb = sum(b.imbalance for b in self._buckets)
        return total_imb / len(self._buckets)

    @property
    def bucket_count(self) -> int:
        return len(self._buckets)

    @property
    def completed_buckets(self) -> List[VpinBucket]:
        return list(self._buckets)

    @property
    def toxicity_label(self) -> str:
        v = self.current
        if v >= 0.7:
            return "HIGH"
        elif v >= 0.4:
            return "MEDIUM"
        return "LOW"

    def pending_volume(self) -> int:
        return self._cur_buy + self._cur_sell

    def __str__(self) -> str:
        return (
            f"VPIN={self.current:.3f} [{self.toxicity_label}] "
            f"buckets={self.bucket_count}/{self._window}"
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _close_bucket(self) -> None:
        self._buckets.append(VpinBucket(
            buy_vol  = self._cur_buy,
            sell_vol = self._cur_sell,
        ))
        self._cur_buy  = 0
        self._cur_sell = 0
