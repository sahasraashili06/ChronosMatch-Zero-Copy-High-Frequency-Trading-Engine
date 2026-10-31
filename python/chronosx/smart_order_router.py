"""
ChronosX -- Smart Order Router (SOR)

Splits a large parent order across multiple venues to minimise
market impact and get the best average fill price.

Routing strategies:
  - BestPrice  : send entire order to venue with best quoted price
  - ProRata    : split proportional to each venue's available size
  - TWAP slice : equal slices across venues (ignores price ranking)

Each venue is represented by a VenueQuote (bid/ask + available qty).
The router returns a list of VenueOrder (venue_id, qty) slices.

Usage:
    sor = SmartOrderRouter(strategy=RoutingStrategy.ProRata)

    quotes = [
        VenueQuote("NYSE",   ask=100_100, ask_qty=500),
        VenueQuote("NASDAQ", ask=100_050, ask_qty=300),
        VenueQuote("BATS",   ask=100_200, ask_qty=800),
    ]

    slices = sor.route_buy(qty=600, quotes=quotes)
    for s in slices:
        print(f"Send {s.qty} to {s.venue_id}")
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import List

from .types import PRICE_MULT


class RoutingStrategy(IntEnum):
    BestPrice = 0   # all to cheapest venue
    ProRata   = 1   # split by available size
    EqualSplit = 2  # split evenly across venues


@dataclass
class VenueQuote:
    venue_id:  str
    bid:       int = 0    # fixed-point
    ask:       int = 0
    bid_qty:   int = 0
    ask_qty:   int = 0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass
class VenueOrder:
    venue_id: str
    qty:      int
    price:    int   # limit price to use (fixed-point)

    @property
    def notional_usd(self) -> float:
        return (self.qty * self.price) / PRICE_MULT


class SmartOrderRouter:
    """
    Routes parent orders across venues to minimise cost.

    Args:
        strategy: BestPrice, ProRata, or EqualSplit.
        min_qty : Minimum slice size per venue (avoid tiny orders).
    """

    def __init__(
        self,
        strategy: RoutingStrategy = RoutingStrategy.ProRata,
        min_qty:  int = 1,
    ) -> None:
        if min_qty < 1:
            raise ValueError("min_qty must be >= 1")
        self._strategy = strategy
        self._min_qty  = min_qty
        self._routed:  int = 0   # total qty routed so far

    # ── Public API ────────────────────────────────────────────────────────────

    def route_buy(
        self,
        qty:    int,
        quotes: List[VenueQuote],
    ) -> List[VenueOrder]:
        """
        Route a BUY order of *qty* shares across venues.
        Uses the ask side of each VenueQuote.
        """
        eligible = [q for q in quotes if q.ask > 0 and q.ask_qty > 0]
        if not eligible or qty <= 0:
            return []

        eligible.sort(key=lambda q: q.ask)   # cheapest first
        slices = self._split(qty, eligible, side="ask")
        self._routed += qty
        return slices

    def route_sell(
        self,
        qty:    int,
        quotes: List[VenueQuote],
    ) -> List[VenueOrder]:
        """
        Route a SELL order of *qty* shares across venues.
        Uses the bid side of each VenueQuote.
        """
        eligible = [q for q in quotes if q.bid > 0 and q.bid_qty > 0]
        if not eligible or qty <= 0:
            return []

        eligible.sort(key=lambda q: q.bid, reverse=True)  # highest bid first
        slices = self._split(qty, eligible, side="bid")
        self._routed += qty
        return slices

    @property
    def total_routed(self) -> int:
        return self._routed

    @property
    def strategy(self) -> RoutingStrategy:
        return self._strategy

    def reset(self) -> None:
        self._routed = 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _split(
        self,
        qty:      int,
        venues:   List[VenueQuote],
        side:     str,
    ) -> List[VenueOrder]:

        if self._strategy == RoutingStrategy.BestPrice:
            return self._best_price(qty, venues, side)
        elif self._strategy == RoutingStrategy.ProRata:
            return self._pro_rata(qty, venues, side)
        else:
            return self._equal_split(qty, venues, side)

    def _best_price(self, qty, venues, side) -> List[VenueOrder]:
        """Send as much as possible to best venue, overflow to next."""
        result = []
        remaining = qty
        for v in venues:
            if remaining <= 0:
                break
            avail = v.ask_qty if side == "ask" else v.bid_qty
            price = v.ask    if side == "ask" else v.bid
            fill  = min(remaining, avail)
            if fill >= self._min_qty:
                result.append(VenueOrder(venue_id=v.venue_id, qty=fill, price=price))
                remaining -= fill
        return result

    def _pro_rata(self, qty, venues, side) -> List[VenueOrder]:
        """Split proportional to available size at each venue."""
        total_avail = sum(
            (v.ask_qty if side == "ask" else v.bid_qty) for v in venues
        )
        if total_avail == 0:
            return []

        result     = []
        remaining  = qty
        last_venue = None

        for i, v in enumerate(venues):
            avail = v.ask_qty if side == "ask" else v.bid_qty
            price = v.ask    if side == "ask" else v.bid
            share = int(qty * avail / total_avail)
            share = min(share, avail, remaining)
            if share >= self._min_qty:
                result.append(VenueOrder(venue_id=v.venue_id, qty=share, price=price))
                remaining -= share
                last_venue = (v, price)

        # assign leftover to last venue
        if remaining > 0 and last_venue:
            v, price = last_venue
            for ro in result:
                if ro.venue_id == v.venue_id:
                    ro.qty += remaining
                    remaining = 0
                    break

        return result

    def _equal_split(self, qty, venues, side) -> List[VenueOrder]:
        """Split evenly across venues."""
        n         = len(venues)
        base      = qty // n
        leftover  = qty % n
        result    = []
        for i, v in enumerate(venues):
            price = v.ask if side == "ask" else v.bid
            avail = v.ask_qty if side == "ask" else v.bid_qty
            share = base + (1 if i < leftover else 0)
            share = min(share, avail)
            if share >= self._min_qty:
                result.append(VenueOrder(venue_id=v.venue_id, qty=share, price=price))
        return result
