"""
ChronosX -- Market Data Publisher

Publishes order book snapshots and trade events to subscribers via
a simple in-process pub/sub bus.  Simulates what an exchange's
market-data feed handler would emit to downstream consumers.

Architecture:
    MatchingEngine  --events-->  MarketDataPublisher  --dispatch-->  subscribers
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from .types import Side, TradeEvent, PRICE_MULT


# ── Snapshot types ────────────────────────────────────────────────────────────

@dataclass
class PriceLevelSnapshot:
    """A single price level in a book snapshot."""
    price: int
    qty:   int
    count: int   # number of resting orders

    def price_str(self) -> str:
        return f"${self.price / PRICE_MULT:.4f}"


@dataclass
class BookSnapshot:
    """Top-N bid/ask snapshot emitted after every order event."""
    instrument_id: str
    seq:           int
    timestamp_ns:  int
    bids:          List[PriceLevelSnapshot] = field(default_factory=list)
    asks:          List[PriceLevelSnapshot] = field(default_factory=list)

    @property
    def best_bid(self) -> Optional[PriceLevelSnapshot]:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Optional[PriceLevelSnapshot]:
        return self.asks[0] if self.asks else None

    @property
    def spread(self) -> Optional[int]:
        if self.best_bid and self.best_ask:
            return self.best_ask.price - self.best_bid.price
        return None

    def spread_str(self) -> str:
        s = self.spread
        return f"${s / PRICE_MULT:.4f}" if s is not None else "N/A"


@dataclass
class TradeReport:
    """A public trade report broadcast to all subscribers."""
    instrument_id: str
    seq:           int
    timestamp_ns:  int
    aggressor_id:  int
    resting_id:    int
    price:         int
    qty:           int
    aggressor_side: Side

    def price_str(self) -> str:
        return f"${self.price / PRICE_MULT:.4f}"


# ── Subscriber type aliases ───────────────────────────────────────────────────

BookSubscriber  = Callable[[BookSnapshot], None]
TradeSubscriber = Callable[[TradeReport], None]


# ── Publisher ─────────────────────────────────────────────────────────────────

class MarketDataPublisher:
    """
    Collects events from the matching engine and fans them out to
    registered subscriber callbacks.

    Usage:
        pub = MarketDataPublisher("AAPL", depth=5)
        pub.subscribe_book(lambda snap: print(snap))
        pub.subscribe_trades(lambda t: print(t))

        # After each OMS submit:
        pub.on_order_event(engine.book, trades, aggressor_side)
    """

    def __init__(self, instrument_id: str = "SIM", depth: int = 5) -> None:
        self._instrument_id = instrument_id
        self._depth         = depth
        self._seq:          int = 0
        self._book_subs:    List[BookSubscriber]  = []
        self._trade_subs:   List[TradeSubscriber] = []

    # ── Subscription API ──────────────────────────────────────────────────────

    def subscribe_book(self, fn: BookSubscriber) -> None:
        self._book_subs.append(fn)

    def subscribe_trades(self, fn: TradeSubscriber) -> None:
        self._trade_subs.append(fn)

    def unsubscribe_book(self, fn: BookSubscriber) -> None:
        self._book_subs = [s for s in self._book_subs if s is not fn]

    def unsubscribe_trades(self, fn: TradeSubscriber) -> None:
        self._trade_subs = [s for s in self._trade_subs if s is not fn]

    # ── Event ingestion ───────────────────────────────────────────────────────

    def on_order_event(
        self,
        book,                          # OrderBook
        trades: List[TradeEvent],
        aggressor_side: Side,
    ) -> None:
        """Call this after every OMS submit/cancel to push updates."""
        self._seq += 1
        now = time.time_ns()

        # 1. Publish trade reports
        if trades and self._trade_subs:
            for t in trades:
                report = TradeReport(
                    instrument_id  = self._instrument_id,
                    seq            = self._seq,
                    timestamp_ns   = now,
                    aggressor_id   = t.aggressor_id,
                    resting_id     = t.resting_id,
                    price          = t.price,
                    qty            = t.qty,
                    aggressor_side = aggressor_side,
                )
                for sub in self._trade_subs:
                    sub(report)

        # 2. Publish book snapshot
        if self._book_subs:
            snap = self._build_snapshot(book, now)
            for sub in self._book_subs:
                sub(snap)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_snapshot(self, book, timestamp_ns: int) -> BookSnapshot:
        snap = BookSnapshot(
            instrument_id = self._instrument_id,
            seq           = self._seq,
            timestamp_ns  = timestamp_ns,
        )

        # Bids — descending price
        bids_map = book._bids
        bid_prices = sorted(bids_map.keys(), reverse=True)[: self._depth]
        for price in bid_prices:
            lvl = bids_map[price]
            snap.bids.append(PriceLevelSnapshot(
                price=price, qty=lvl.total_qty, count=lvl.order_count
            ))

        # Asks — ascending price
        asks_map = book._asks
        ask_prices = sorted(asks_map.keys())[: self._depth]
        for price in ask_prices:
            lvl = asks_map[price]
            snap.asks.append(PriceLevelSnapshot(
                price=price, qty=lvl.total_qty, count=lvl.order_count
            ))

        return snap
