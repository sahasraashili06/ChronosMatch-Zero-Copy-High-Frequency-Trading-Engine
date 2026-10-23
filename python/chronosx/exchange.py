"""
ChronosX -- Multi-Instrument Exchange

Routes orders to the correct per-instrument OrderBook.
Supports dynamic instrument registration, cross-instrument
position aggregation, and per-instrument statistics.

Architecture:
    Exchange
      ├── Instrument("AAPL")  -> MatchingEngine + MarketDataPublisher
      ├── Instrument("GOOGL") -> MatchingEngine + MarketDataPublisher
      └── Instrument("TSLA")  -> MatchingEngine + MarketDataPublisher
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .types import Side, OrderType, OrderStatus, PRICE_MULT
from .risk_engine import RiskEngine, RiskLimits
from .matching_engine import MatchingEngine
from .oms import OrderManagementSystem, OrderRequest, OmsResponse
from .market_data import MarketDataPublisher, BookSnapshot
from .stats import SessionStats


@dataclass
class InstrumentInfo:
    """Metadata for a listed instrument."""
    symbol:     str
    tick_size:  int = 1          # minimum price increment in ticks
    lot_size:   int = 1          # minimum order qty
    ref_price:  int = 100_000   # reference price in ticks ($10.0000)


class InstrumentSession:
    """One instrument's complete trading session."""

    def __init__(self, info: InstrumentInfo, risk: RiskEngine) -> None:
        self._info  = info
        self._oms   = OrderManagementSystem(risk)
        self._pub   = MarketDataPublisher(info.symbol, depth=10)
        self._stats = SessionStats()

    @property
    def symbol(self) -> str:
        return self._info.symbol

    @property
    def info(self) -> InstrumentInfo:
        return self._info

    @property
    def oms(self) -> OrderManagementSystem:
        return self._oms

    @property
    def publisher(self) -> MarketDataPublisher:
        return self._pub

    @property
    def stats(self) -> SessionStats:
        return self._stats

    def submit(self, req: OrderRequest) -> OmsResponse:
        resp = self._oms.submit(req)
        mr   = resp.match_result

        self._stats.record_order(
            submitted = True,
            filled    = mr.final_status == OrderStatus.Filled,
            partial   = mr.final_status == OrderStatus.PartiallyFilled,
            cancelled = mr.final_status == OrderStatus.Cancelled,
            rejected  = mr.final_status == OrderStatus.Rejected,
        )
        for t in mr.trades:
            self._stats.record_trade(t)

        self._pub.on_order_event(self._oms.book, mr.trades, req.side)
        return resp

    def cancel(self, order_id: int) -> OmsResponse:
        resp = self._oms.cancel(order_id)
        self._pub.on_order_event(self._oms.book, [], Side.Buy)
        return resp

    def best_bid(self) -> Optional[int]:
        return self._oms.book.best_bid()

    def best_ask(self) -> Optional[int]:
        return self._oms.book.best_ask()

    def spread(self) -> Optional[int]:
        return self._oms.book.spread()

    def mid_price(self) -> Optional[float]:
        bb, ba = self.best_bid(), self.best_ask()
        return (bb + ba) / 2.0 if bb is not None and ba is not None else None

    def print_summary(self) -> None:
        bb  = self.best_bid()
        ba  = self.best_ask()
        sp  = self.spread()
        mid = self.mid_price()
        print(f"\n  [{self.symbol}]")
        print(f"    Best Bid   : ${bb / PRICE_MULT:.4f}" if bb else "    Best Bid   : N/A")
        print(f"    Best Ask   : ${ba / PRICE_MULT:.4f}" if ba else "    Best Ask   : N/A")
        print(f"    Spread     : ${sp / PRICE_MULT:.4f}" if sp else "    Spread     : N/A")
        print(f"    Mid Price  : ${mid / PRICE_MULT:.4f}" if mid else "    Mid Price  : N/A")
        print(f"    Trades     : {self._stats.trade_count:,}")
        print(f"    Volume     : {self._stats.total_qty:,}")
        print(f"    VWAP       : {self._stats.vwap_str}")
        print(f"    Fill Rate  : {self._stats.fill_rate:.1%}")


class Exchange:
    """
    Multi-instrument exchange router.

    Usage:
        ex = Exchange()
        ex.list_instrument(InstrumentInfo("AAPL", ref_price=182_000))
        ex.list_instrument(InstrumentInfo("GOOGL", ref_price=140_000))

        ex.submit("AAPL",  OrderRequest(id=1, side=Side.Buy,  ...))
        ex.submit("GOOGL", OrderRequest(id=2, side=Side.Sell, ...))

        ex.print_market_summary()
    """

    def __init__(self, risk: Optional[RiskEngine] = None) -> None:
        self._risk   = risk or RiskEngine()
        self._instruments: Dict[str, InstrumentSession] = {}

    # ── Instrument management ─────────────────────────────────────────────────

    def list_instrument(self, info: InstrumentInfo) -> None:
        """Add a new instrument to the exchange."""
        if info.symbol in self._instruments:
            raise ValueError(f"Instrument {info.symbol!r} already listed")
        self._instruments[info.symbol] = InstrumentSession(info, self._risk)

    def delist_instrument(self, symbol: str) -> None:
        self._instruments.pop(symbol, None)

    def symbols(self) -> List[str]:
        return list(self._instruments.keys())

    def session(self, symbol: str) -> InstrumentSession:
        if symbol not in self._instruments:
            raise KeyError(f"Unknown instrument: {symbol!r}")
        return self._instruments[symbol]

    # ── Order routing ─────────────────────────────────────────────────────────

    def submit(self, symbol: str, req: OrderRequest) -> OmsResponse:
        return self.session(symbol).submit(req)

    def cancel(self, symbol: str, order_id: int) -> OmsResponse:
        return self.session(symbol).cancel(order_id)

    def subscribe_book(self, symbol: str, fn) -> None:
        self.session(symbol).publisher.subscribe_book(fn)

    def subscribe_trades(self, symbol: str, fn) -> None:
        self.session(symbol).publisher.subscribe_trades(fn)

    # ── Market-wide queries ───────────────────────────────────────────────────

    def total_trade_count(self) -> int:
        return sum(s.stats.trade_count for s in self._instruments.values())

    def total_volume(self) -> int:
        return sum(s.stats.total_qty for s in self._instruments.values())

    def print_market_summary(self) -> None:
        print("\n" + "=" * 50)
        print("  ChronosX Exchange -- Market Summary")
        print("=" * 50)
        print(f"  Instruments listed : {len(self._instruments)}")
        print(f"  Total trades       : {self.total_trade_count():,}")
        print(f"  Total volume       : {self.total_volume():,}")
        for sym, sess in sorted(self._instruments.items()):
            sess.print_summary()
        print()
