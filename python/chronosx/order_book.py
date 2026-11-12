"""
ChronosX — OrderBook

Maintains two sides (bids / asks) as sorted dicts of PriceLevels.
- Bids: sorted descending  → best_bid = max key
- Asks: sorted ascending   → best_ask = min key

Uses sortedcontainers.SortedDict for O(log N_prices) operations.
Falls back to plain dict + sort if sortedcontainers is unavailable.
"""
from __future__ import annotations
from typing import Dict, Optional

try:
    from sortedcontainers import SortedDict   # type: ignore
    _HAS_SORTED = True
except ImportError:
    _HAS_SORTED = False

from .types import Side, INVALID_PRICE
from .price_level import PriceLevel
from .memory_pool import ObjectPool
from .order import Order, NULL_IDX


class OrderBook:
    """Limit Order Book with price-time priority (FIFO within a level)."""

    def __init__(self, pool: ObjectPool) -> None:
        self._pool = pool
        # bids: negated-key SortedDict so the "smallest" key = best bid
        if _HAS_SORTED:
            self._bids: Dict[int, PriceLevel] = SortedDict(lambda k: -k)
            self._asks: Dict[int, PriceLevel] = SortedDict()
        else:
            self._bids = {}
            self._asks = {}
        self._order_index: Dict[int, int] = {}  # order_id → pool index
        self._active_count: int = 0

    # ── Book queries ─────────────────────────────────────────────────────────

    def best_bid(self) -> Optional[int]:
        if not self._bids:
            return None
        return next(iter(self._bids)) if _HAS_SORTED else max(self._bids)

    def best_ask(self) -> Optional[int]:
        if not self._asks:
            return None
        return next(iter(self._asks)) if _HAS_SORTED else min(self._asks)

    def spread(self) -> Optional[int]:
        bb, ba = self.best_bid(), self.best_ask()
        return (ba - bb) if bb is not None and ba is not None else None

    def is_empty(self) -> bool:
        return not self._bids and not self._asks

    def bid_levels(self) -> int:
        return len(self._bids)

    def ask_levels(self) -> int:
        return len(self._asks)

    def active_order_count(self) -> int:
        return self._active_count

    def bid_qty_at(self, price: int) -> int:
        lvl = self._bids.get(price)
        return lvl.total_qty if lvl else 0

    def ask_qty_at(self, price: int) -> int:
        lvl = self._asks.get(price)
        return lvl.total_qty if lvl else 0

    def top_bids(self, depth: int = 5) -> list:
        """Return [(price, qty), ...] for top *depth* bid levels (best first)."""
        prices = (sorted(self._bids.keys(), reverse=True)
                  if not _HAS_SORTED else list(self._bids.keys()))
        return [(p, self._bids[p].total_qty) for p in prices[:depth]]

    def top_asks(self, depth: int = 5) -> list:
        """Return [(price, qty), ...] for top *depth* ask levels (best first)."""
        prices = (sorted(self._asks.keys())
                  if not _HAS_SORTED else list(self._asks.keys()))
        return [(p, self._asks[p].total_qty) for p in prices[:depth]]

    def find_order_idx(self, order_id: int) -> int:
        return self._order_index.get(order_id, NULL_IDX)

    # ── Mutation ─────────────────────────────────────────────────────────────

    def add_order(self, idx: int) -> None:
        order = self._pool.at(idx)
        book  = self._bids if order.side == Side.Buy else self._asks
        price = order.price

        if price not in book:
            book[price] = PriceLevel()
        book[price].add_order(idx, self._pool)
        self._order_index[order.order_id] = idx
        self._active_count += 1

    def cancel_order(self, order_id: int) -> bool:
        idx = self._order_index.get(order_id, NULL_IDX)
        if idx == NULL_IDX:
            return False
        order = self._pool.at(idx)
        book  = self._bids if order.side == Side.Buy else self._asks
        price = order.price
        lvl   = book.get(price)
        if lvl is None:
            return False
        lvl.remove_order(idx, self._pool)
        if lvl.empty:
            del book[price]
        del self._order_index[order_id]
        self._active_count -= 1
        return True

    def front_ask_idx(self) -> int:
        ba = self.best_ask()
        if ba is None:
            return NULL_IDX
        return self._asks[ba].front_idx

    def front_bid_idx(self) -> int:
        bb = self.best_bid()
        if bb is None:
            return NULL_IDX
        return self._bids[bb].front_idx

    def reduce_front_qty(self, price: int, side: Side, delta: int) -> None:
        book = self._bids if side == Side.Buy else self._asks
        lvl  = book.get(price)
        if lvl:
            lvl.reduce_front_qty(delta)

    def remove_front(self, price: int, side: Side) -> None:
        """Remove the front order from level *price* on *side*."""
        book = self._bids if side == Side.Buy else self._asks
        lvl  = book.get(price)
        if lvl is None:
            return
        front_idx = lvl.front_idx
        if front_idx == NULL_IDX:
            return
        front_order = self._pool.at(front_idx)
        lvl.remove_order(front_idx, self._pool)
        self._order_index.pop(front_order.order_id, None)
        if lvl.empty:
            del book[price]
        self._active_count -= 1
