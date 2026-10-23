"""
ChronosX -- Order Book Imbalance Indicator

Computes bid/ask volume imbalance from the order book — one of the most
widely-used short-term alpha signals in HFT.

    Imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty)
    Range: -1.0 (full ask pressure) to +1.0 (full bid pressure)

Variants:
  - Weighted : weight each level by 1/rank (top level counts most)
  - Fixed-depth: only look at top N price levels
  - Queue imbalance: best-bid qty vs best-ask qty only
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .order_book import OrderBook


@dataclass
class ImbalanceReading:
    """A single imbalance measurement."""
    depth:           int    # number of levels used
    bid_qty:         int    # total bid quantity
    ask_qty:         int    # total ask quantity
    raw:             float  # (bid - ask) / (bid + ask), in [-1, +1]
    weighted:        float  # depth-weighted version
    queue_imbalance: float  # (best-bid-qty - best-ask-qty) / sum

    @property
    def direction(self) -> str:
        if self.raw > 0.1:
            return "BUY_PRESSURE"
        elif self.raw < -0.1:
            return "SELL_PRESSURE"
        return "NEUTRAL"

    def __str__(self) -> str:
        return (
            f"Imbalance(raw={self.raw:+.3f}  "
            f"weighted={self.weighted:+.3f}  "
            f"queue={self.queue_imbalance:+.3f}  "
            f"[{self.direction}]  "
            f"depth={self.depth}  "
            f"bid={self.bid_qty}  ask={self.ask_qty})"
        )


class OrderBookImbalance:
    """
    Computes order book imbalance signals from a live OrderBook.

    Usage:
        obi = OrderBookImbalance(depth=5)
        reading = obi.compute(book)
        print(reading)

        # Rolling EMA:
        obi.update(book)
        print(f"EMA: {obi.ema:.3f}")
    """

    def __init__(self, depth: int = 5, ema_alpha: float = 0.1) -> None:
        self._depth  = depth
        self._alpha  = ema_alpha
        self._ema:   Optional[float] = None
        self._last:  Optional[ImbalanceReading] = None
        self._count: int = 0

    # ── Core ──────────────────────────────────────────────────────────────────

    def compute(self, book: OrderBook) -> Optional[ImbalanceReading]:
        """Return an ImbalanceReading for the current book state."""
        bids = book.top_bids(self._depth)   # [(price, qty), ...]
        asks = book.top_asks(self._depth)

        if not bids and not asks:
            return None

        bid_qty = sum(qty for _, qty in bids)
        ask_qty = sum(qty for _, qty in asks)
        total   = bid_qty + ask_qty
        if total == 0:
            return None

        raw      = (bid_qty - ask_qty) / total
        weighted = self._weighted(bids, asks)

        bb_qty = bids[0][1] if bids else 0
        ba_qty = asks[0][1] if asks else 0
        q_tot  = bb_qty + ba_qty
        queue  = (bb_qty - ba_qty) / q_tot if q_tot > 0 else 0.0

        return ImbalanceReading(
            depth=self._depth, bid_qty=bid_qty, ask_qty=ask_qty,
            raw=raw, weighted=weighted, queue_imbalance=queue,
        )

    def update(self, book: OrderBook) -> Optional[ImbalanceReading]:
        """Compute + update EMA. Returns the latest reading."""
        r = self.compute(book)
        if r is None:
            return None
        self._last   = r
        self._count += 1
        self._ema    = r.raw if self._ema is None else (
            self._alpha * r.raw + (1 - self._alpha) * self._ema
        )
        return r

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def ema(self) -> Optional[float]:
        return self._ema

    @property
    def last(self) -> Optional[ImbalanceReading]:
        return self._last

    @property
    def count(self) -> int:
        return self._count

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _weighted(bids, asks) -> float:
        bid_w = sum(qty / (i + 1) for i, (_, qty) in enumerate(bids))
        ask_w = sum(qty / (i + 1) for i, (_, qty) in enumerate(asks))
        total = bid_w + ask_w
        return (bid_w - ask_w) / total if total else 0.0
