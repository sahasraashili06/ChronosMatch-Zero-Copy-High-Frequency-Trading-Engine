"""
ChronosX — Simulator

Runs deterministic scenario replays and a live SPSC throughput demo.
"""
from __future__ import annotations
import time
import threading
from dataclasses import dataclass, field
from enum import auto, Enum
from typing import List

from .types import Side, OrderType, PRICE_MULT
from .risk_engine import RiskEngine
from .oms import OrderManagementSystem, OrderRequest, OmsResponse
from .spsc_ring_buffer import SpscRingBuffer
from .order_book import OrderBook

SIM_RING_CAPACITY = 4096


class EventKind(Enum):
    NewOrder = auto()
    Cancel   = auto()


@dataclass
class ScenarioEvent:
    kind:      EventKind    = EventKind.NewOrder
    req:       OrderRequest = field(default_factory=OrderRequest)
    cancel_id: int          = 0


class Simulator:
    """Runs named scenarios and reports results."""

    def __init__(self) -> None:
        self._risk = RiskEngine()
        self._oms  = OrderManagementSystem(self._risk)

    # ── Scenario replay ───────────────────────────────────────────────────────

    def run_scenario(self, events: List[ScenarioEvent]) -> List[OmsResponse]:
        results: List[OmsResponse] = []
        for ev in events:
            if ev.kind == EventKind.NewOrder:
                results.append(self._oms.submit(ev.req))
            else:
                results.append(self._oms.cancel(ev.cancel_id))
        return results

    # ── SPSC throughput demo ──────────────────────────────────────────────────

    def run_spsc_demo(self, num_events: int = 100_000) -> float:
        """Returns throughput in orders/second."""
        ring: SpscRingBuffer[OrderRequest] = SpscRingBuffer(SIM_RING_CAPACITY)
        done      = threading.Event()
        consumed  = [0]
        produced  = [0]

        fresh_risk = RiskEngine()
        fresh_oms  = OrderManagementSystem(fresh_risk)

        def producer() -> None:
            for i in range(num_events):
                req = OrderRequest(
                    id    = i + 1,
                    side  = Side.Buy if i % 2 == 0 else Side.Sell,
                    type  = OrderType.Limit,
                    price = 100_000 + (i % 100),
                    qty   = 10,
                )
                while not ring.push(req):
                    pass   # busy-spin if full
                produced[0] += 1
            done.set()

        t_start = time.perf_counter()
        prod_thread = threading.Thread(target=producer, daemon=True)
        prod_thread.start()

        while not done.is_set() or not ring.empty():
            item = ring.pop()
            if item is not None:
                fresh_oms.submit(item)
                consumed[0] += 1

        while True:
            item = ring.pop()
            if item is None:
                break
            fresh_oms.submit(item)
            consumed[0] += 1

        t_end = time.perf_counter()
        prod_thread.join()
        elapsed = t_end - t_start
        return consumed[0] / elapsed if elapsed > 0 else 0.0

    # ── Reporting helpers ─────────────────────────────────────────────────────

    def print_summary(self) -> None:
        book = self._oms.book
        bb   = book.best_bid()
        ba   = book.best_ask()
        sp   = book.spread()

        print("\n=== ChronosX Simulator Summary ===")
        print(f"  Total orders tracked : {self._oms.order_count}")
        print(f"  Active book orders   : {book.active_order_count()}")
        print(f"  Bid levels           : {book.bid_levels()}")
        print(f"  Ask levels           : {book.ask_levels()}")
        print(f"  Best bid             : {bb} ticks (${bb/PRICE_MULT:.4f})" if bb else "  Best bid             : N/A")
        print(f"  Best ask             : {ba} ticks (${ba/PRICE_MULT:.4f})" if ba else "  Best ask             : N/A")
        print(f"  Spread               : {sp} ticks" if sp is not None else "  Spread               : N/A")

    @property
    def book(self) -> OrderBook:
        return self._oms.book
