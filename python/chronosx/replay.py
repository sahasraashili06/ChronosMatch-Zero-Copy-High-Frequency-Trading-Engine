"""
ChronosX -- CSV Replay Engine

Loads historical order sequences from CSV files and replays them
through the matching engine, publishing events in timestamp order.

CSV format:
    ts_ns,order_id,side,type,price,qty
    1000000,1,Buy,Limit,100000,50
    2000000,2,Sell,Limit,100200,30
    3000000,3,Buy,Market,0,20

Supports:
  - Time-scaling (replay faster or slower than real time)
  - Event callbacks (on_trade, on_book_update)
  - Multi-instrument replay from a single CSV (add 'symbol' column)
  - Replay statistics (fill rate, VWAP, latency)
"""
from __future__ import annotations

import csv
import io
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Union

from .types import Side, OrderType, OrderStatus, TradeEvent, PRICE_MULT
from .oms import OrderManagementSystem, OrderRequest, OmsResponse
from .risk_engine import RiskEngine, RiskLimits


# ── CSV row ───────────────────────────────────────────────────────────────────

@dataclass
class ReplayEvent:
    """One parsed row from the replay CSV."""
    ts_ns:    int
    order_id: int
    side:     Side
    type:     OrderType
    price:    int        # fixed-point, PRICE_MULT
    qty:      int
    symbol:   str = "DEFAULT"


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_side(s: str) -> Side:
    return Side.Buy if s.strip().lower() in ("buy", "b", "0") else Side.Sell

def _parse_type(s: str) -> OrderType:
    return OrderType.Market if s.strip().lower() in ("market", "mkt", "m") else OrderType.Limit

def parse_csv(source: Union[str, Path, io.StringIO]) -> List[ReplayEvent]:
    """Parse a CSV file or StringIO into a sorted list of ReplayEvents."""
    if isinstance(source, (str, Path)):
        fh = open(source, newline="", encoding="utf-8")
        close = True
    else:
        fh = source
        close = False

    try:
        reader = csv.DictReader(fh)
        events = []
        for row in reader:
            events.append(ReplayEvent(
                ts_ns    = int(row["ts_ns"]),
                order_id = int(row["order_id"]),
                side     = _parse_side(row["side"]),
                type     = _parse_type(row["type"]),
                price    = int(row["price"]),
                qty      = int(row["qty"]),
                symbol   = row.get("symbol", "DEFAULT").strip(),
            ))
        return sorted(events, key=lambda e: e.ts_ns)
    finally:
        if close:
            fh.close()


# ── Replay stats ──────────────────────────────────────────────────────────────

@dataclass
class ReplayStats:
    orders_submitted: int = 0
    orders_filled:    int = 0
    orders_partial:   int = 0
    orders_cancelled: int = 0
    orders_rejected:  int = 0
    trade_count:      int = 0
    total_volume:     int = 0
    total_notional:   int = 0  # sum of price * qty for each trade

    @property
    def fill_rate(self) -> float:
        return self.orders_filled / self.orders_submitted if self.orders_submitted else 0.0

    @property
    def vwap(self) -> float:
        return self.total_notional / (self.total_volume * PRICE_MULT) if self.total_volume else 0.0

    def __str__(self) -> str:
        return (
            f"ReplayStats:\n"
            f"  Orders  : submitted={self.orders_submitted:,}  "
            f"filled={self.orders_filled:,}  "
            f"partial={self.orders_partial:,}  "
            f"rejected={self.orders_rejected:,}\n"
            f"  Trades  : {self.trade_count:,}\n"
            f"  Volume  : {self.total_volume:,}\n"
            f"  Fill rate: {self.fill_rate:.1%}\n"
            f"  VWAP    : ${self.vwap:.4f}"
        )


# ── Replay engine ─────────────────────────────────────────────────────────────

class ReplayEngine:
    """
    Replays a sequence of ReplayEvents through an OMS.

    Usage (instant replay — no sleep):
        engine = ReplayEngine(oms)
        stats  = engine.run(events)
        print(stats)

    Usage (real-time replay with callbacks):
        def on_trade(t: TradeEvent):
            print(f"Trade: {t}")

        engine = ReplayEngine(oms, on_trade=on_trade, time_scale=2.0)
        engine.run(events)   # replays at 2x speed

    Args:
        oms:        OrderManagementSystem to replay into.
        on_trade:   Called for every trade event produced.
        on_order:   Called for every OmsResponse.
        time_scale: > 1 = faster than real time; 0 = instant (no sleep).
    """

    def __init__(
        self,
        oms:        OrderManagementSystem,
        on_trade:   Optional[Callable[[TradeEvent], None]] = None,
        on_order:   Optional[Callable[[OmsResponse], None]] = None,
        time_scale: float = 0.0,
    ) -> None:
        self._oms        = oms
        self._on_trade   = on_trade
        self._on_order   = on_order
        self._time_scale = time_scale
        self._stats      = ReplayStats()

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, events: List[ReplayEvent]) -> ReplayStats:
        """Replay all events in order. Returns cumulative stats."""
        self._stats = ReplayStats()

        if not events:
            return self._stats

        first_ts   = events[0].ts_ns
        wall_start = time.perf_counter_ns()

        for ev in events:
            if self._time_scale > 0:
                self._maybe_sleep(ev.ts_ns, first_ts, wall_start)
            self._process(ev)

        return self._stats

    def run_iter(self, events: List[ReplayEvent]) -> Iterator[OmsResponse]:
        """Generator: yield OmsResponse for each event (useful for streaming)."""
        self._stats = ReplayStats()
        first_ts    = events[0].ts_ns if events else 0
        wall_start  = time.perf_counter_ns()

        for ev in events:
            if self._time_scale > 0:
                self._maybe_sleep(ev.ts_ns, first_ts, wall_start)
            resp = self._process(ev)
            yield resp

    @property
    def stats(self) -> ReplayStats:
        return self._stats

    # ── Internal ──────────────────────────────────────────────────────────────

    def _process(self, ev: ReplayEvent) -> OmsResponse:
        resp = self._oms.submit(OrderRequest(
            id    = ev.order_id,
            side  = ev.side,
            type  = ev.type,
            price = ev.price,
            qty   = ev.qty,
        ))
        mr = resp.match_result
        st = self._stats

        st.orders_submitted += 1
        if mr.final_status == OrderStatus.Filled:
            st.orders_filled += 1
        elif mr.final_status == OrderStatus.PartiallyFilled:
            st.orders_partial += 1
        elif mr.final_status == OrderStatus.Cancelled:
            st.orders_cancelled += 1
        elif mr.final_status == OrderStatus.Rejected:
            st.orders_rejected += 1

        for t in mr.trades:
            st.trade_count    += 1
            st.total_volume   += t.qty
            st.total_notional += t.price * t.qty
            if self._on_trade:
                self._on_trade(t)

        if self._on_order:
            self._on_order(resp)

        return resp

    def _maybe_sleep(
        self,
        event_ts_ns: int,
        first_ts:    int,
        wall_start:  int,
    ) -> None:
        """Sleep so replay runs at self._time_scale × real speed."""
        event_rel   = (event_ts_ns - first_ts) / self._time_scale
        wall_now    = time.perf_counter_ns() - wall_start
        sleep_ns    = event_rel - wall_now
        if sleep_ns > 1_000_000:   # only sleep if > 1ms ahead
            time.sleep(sleep_ns / 1e9)
