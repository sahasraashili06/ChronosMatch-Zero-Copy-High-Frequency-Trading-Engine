"""
ChronosX -- Market Maker Strategy

A simple inventory-aware market maker that:
1. Quotes a two-sided market (bid + ask) around a reference (mid) price.
2. Skews quotes when inventory is too large to manage risk.
3. Cancels and re-quotes when the market moves beyond a tolerance.

This is a simulation-only strategy — it submits orders to the engine
through the OMS and reacts to book snapshots via the MarketDataPublisher.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .types import Side, OrderType, PRICE_MULT
from .oms import OrderManagementSystem, OrderRequest
from .market_data import BookSnapshot
from .position_manager import PositionManager


@dataclass
class MMConfig:
    """Market maker configuration parameters."""
    participant_id:  int   = 1
    half_spread:     int   = 50       # ticks each side (e.g. 50 = $0.0050)
    order_qty:       int   = 100      # qty per side
    max_inventory:   int   = 500      # absolute net qty before skew kicks in
    skew_per_unit:   int   = 5        # extra ticks per unit of inventory
    requote_ticks:   int   = 20       # re-quote if mid moves > N ticks
    max_orders:      int   = 2        # 1 bid + 1 ask at any time


class MarketMaker:
    """
    Simulation market maker.

    Typical usage:
        oms = OrderManagementSystem(risk)
        pm  = PositionManager()
        mm  = MarketMaker(oms, pm, cfg=MMConfig())

        # Feed snapshots from MarketDataPublisher:
        pub.subscribe_book(mm.on_book_snapshot)

        # Kick off initial quotes at a reference price:
        mm.seed_quotes(ref_price=100_000)
    """

    def __init__(
        self,
        oms:    OrderManagementSystem,
        pm:     PositionManager,
        cfg:    MMConfig | None = None,
    ) -> None:
        self._oms      = oms
        self._pm       = pm
        self._cfg      = cfg or MMConfig()
        self._bid_id:  Optional[int] = None
        self._ask_id:  Optional[int] = None
        self._last_mid: Optional[int] = None
        self._next_id: int = 10_000    # MM order IDs start high to avoid collision
        self._quote_count: int = 0

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def quote_count(self) -> int:
        return self._quote_count

    # ── Public API ────────────────────────────────────────────────────────────

    def seed_quotes(self, ref_price: int) -> None:
        """Place initial two-sided quotes around *ref_price*."""
        self._last_mid = ref_price
        self._place_quotes(ref_price)

    def on_book_snapshot(self, snap: BookSnapshot) -> None:
        """Called by MarketDataPublisher on every book update."""
        if snap.best_bid is None or snap.best_ask is None:
            return

        # Mid price from the current book
        new_mid = (snap.best_bid.price + snap.best_ask.price) // 2

        # Re-quote only if mid moved enough
        if self._last_mid is not None:
            if abs(new_mid - self._last_mid) < self._cfg.requote_ticks:
                return

        self._last_mid = new_mid
        self._cancel_existing()
        self._place_quotes(new_mid)

    def cancel_all(self) -> None:
        """Pull both quotes from the book."""
        self._cancel_existing()

    def status(self) -> str:
        pos = self._pm.get_position(self._cfg.participant_id)
        net = pos.net_qty if pos else 0
        return (
            f"MarketMaker | BidID={self._bid_id} AskID={self._ask_id} "
            f"NetQty={net:+d} LastMid=${(self._last_mid or 0) / PRICE_MULT:.4f} "
            f"Quotes={self._quote_count}"
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _inventory(self) -> int:
        pos = self._pm.get_position(self._cfg.participant_id)
        return pos.net_qty if pos else 0

    def _skew(self) -> int:
        """Skew the mid price to reduce inventory risk."""
        inv = self._inventory()
        max_inv = self._cfg.max_inventory
        if max_inv == 0:
            return 0
        ratio = max(-1.0, min(1.0, inv / max_inv))
        return int(-ratio * self._cfg.skew_per_unit * abs(inv))

    def _place_quotes(self, mid: int) -> None:
        skew      = self._skew()
        half      = self._cfg.half_spread
        bid_price = mid + skew - half
        ask_price = mid + skew + half
        qty       = self._cfg.order_qty

        # Bid
        bid_id = self._next_id
        self._next_id += 1
        self._oms.submit(OrderRequest(
            id    = bid_id,
            side  = Side.Buy,
            type  = OrderType.Limit,
            price = bid_price,
            qty   = qty,
        ))
        self._bid_id = bid_id

        # Ask
        ask_id = self._next_id
        self._next_id += 1
        self._oms.submit(OrderRequest(
            id    = ask_id,
            side  = Side.Sell,
            type  = OrderType.Limit,
            price = ask_price,
            qty   = qty,
        ))
        self._ask_id  = ask_id
        self._quote_count += 1

    def _cancel_existing(self) -> None:
        if self._bid_id is not None:
            self._oms.cancel(self._bid_id)
            self._bid_id = None
        if self._ask_id is not None:
            self._oms.cancel(self._ask_id)
            self._ask_id = None
