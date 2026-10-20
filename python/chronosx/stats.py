"""
ChronosX -- Session Statistics

Computes and tracks real-time trading statistics:
  - VWAP (volume-weighted average price)
  - Spread statistics (mean, min, max)
  - Fill rate (% of orders fully filled)
  - Participation rate (MM volume / total volume)
  - Trade frequency (trades / second)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional
from .types import TradeEvent, PRICE_MULT


@dataclass
class SessionStats:
    """Accumulated statistics for a trading session."""

    # Volume & VWAP
    trade_count:    int   = 0
    total_qty:      int   = 0
    total_notional: int   = 0   # sum of price*qty

    # Spread
    spread_samples: List[int] = field(default_factory=list)

    # Orders
    orders_submitted: int = 0
    orders_filled:    int = 0
    orders_partial:   int = 0
    orders_cancelled: int = 0
    orders_rejected:  int = 0

    # Timing
    session_start_ns: int = field(default_factory=time.time_ns)
    last_trade_ns:    int = 0

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def vwap(self) -> Optional[float]:
        if self.total_qty == 0:
            return None
        return self.total_notional / self.total_qty

    @property
    def vwap_str(self) -> str:
        v = self.vwap
        return f"${v / PRICE_MULT:.4f}" if v is not None else "N/A"

    @property
    def avg_spread(self) -> Optional[float]:
        if not self.spread_samples:
            return None
        return sum(self.spread_samples) / len(self.spread_samples)

    @property
    def min_spread(self) -> Optional[int]:
        return min(self.spread_samples) if self.spread_samples else None

    @property
    def max_spread(self) -> Optional[int]:
        return max(self.spread_samples) if self.spread_samples else None

    @property
    def fill_rate(self) -> float:
        """Fraction of submitted orders that were fully filled."""
        if self.orders_submitted == 0:
            return 0.0
        return self.orders_filled / self.orders_submitted

    @property
    def elapsed_sec(self) -> float:
        return (time.time_ns() - self.session_start_ns) / 1e9

    @property
    def trades_per_sec(self) -> float:
        elapsed = self.elapsed_sec
        return self.trade_count / elapsed if elapsed > 0 else 0.0

    # ── Mutation ──────────────────────────────────────────────────────────────

    def record_trade(self, trade: TradeEvent) -> None:
        self.trade_count    += 1
        self.total_qty      += trade.qty
        self.total_notional += trade.price * trade.qty
        self.last_trade_ns   = time.time_ns()

    def record_spread(self, spread: int) -> None:
        self.spread_samples.append(spread)

    def record_order(
        self,
        submitted: bool = True,
        filled:    bool = False,
        partial:   bool = False,
        cancelled: bool = False,
        rejected:  bool = False,
    ) -> None:
        if submitted:  self.orders_submitted += 1
        if filled:     self.orders_filled    += 1
        if partial:    self.orders_partial   += 1
        if cancelled:  self.orders_cancelled += 1
        if rejected:   self.orders_rejected  += 1

    # ── Reporting ─────────────────────────────────────────────────────────────

    def print_report(self) -> None:
        avg_sp = self.avg_spread
        min_sp = self.min_spread
        max_sp = self.max_spread

        print("\n=== Session Statistics ===")
        print(f"  Session duration  : {self.elapsed_sec:.2f}s")
        print(f"  Trades            : {self.trade_count:,}")
        print(f"  Total volume      : {self.total_qty:,} qty")
        print(f"  Session VWAP      : {self.vwap_str}")
        print(f"  Trade frequency   : {self.trades_per_sec:.1f} trades/sec")
        print()
        print(f"  Orders submitted  : {self.orders_submitted:,}")
        print(f"  Orders filled     : {self.orders_filled:,}")
        print(f"  Orders partial    : {self.orders_partial:,}")
        print(f"  Orders cancelled  : {self.orders_cancelled:,}")
        print(f"  Orders rejected   : {self.orders_rejected:,}")
        print(f"  Fill rate         : {self.fill_rate:.1%}")
        print()
        if avg_sp is not None:
            print(f"  Avg spread        : ${avg_sp / PRICE_MULT:.4f}")
            print(f"  Min spread        : ${min_sp / PRICE_MULT:.4f}")  # type: ignore[operator]
            print(f"  Max spread        : ${max_sp / PRICE_MULT:.4f}")  # type: ignore[operator]
        else:
            print("  Spread data       : N/A")
