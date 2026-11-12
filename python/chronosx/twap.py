"""
ChronosX -- TWAP Execution Algorithm

Time-Weighted Average Price (TWAP) executor.

Splits a large parent order into equal child slices and submits
one slice per time interval, minimising market impact.

                Parent Order (qty=1000, duration=10s)
                     |
         +-----------+-----------+
         |           |           |
      Slice 1     Slice 2    ...Slice N
      (qty=100)  (qty=100)   (qty=100)
      t=0s       t=1s         t=9s

This is simulation-only — slices are submitted synchronously
when you call .tick(), so you control the clock.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional

from .types import Side, OrderType, OrderStatus, PRICE_MULT
from .oms import OrderManagementSystem, OrderRequest, OmsResponse


class TwapState(IntEnum):
    Pending   = 0
    Running   = 1
    Completed = 2
    Cancelled = 3


@dataclass
class TwapConfig:
    """Configuration for a TWAP execution."""
    parent_id:    int        # unique ID for this TWAP job
    side:         Side
    total_qty:    int        # total quantity to execute
    num_slices:   int        # how many child orders to send
    limit_price:  int        # worst-case price limit (0 = market)
    interval_sec: float = 1.0  # seconds between slices (for real clock)

    @property
    def slice_qty(self) -> int:
        return self.total_qty // self.num_slices

    @property
    def remainder_qty(self) -> int:
        return self.total_qty - (self.slice_qty * self.num_slices)


@dataclass
class TwapStatus:
    """Runtime state of a TWAP execution."""
    config:         TwapConfig
    state:          TwapState     = TwapState.Pending
    slices_sent:    int           = 0
    qty_filled:     int           = 0
    qty_submitted:  int           = 0
    avg_fill_price: float         = 0.0
    child_ids:      List[int]     = field(default_factory=list)
    responses:      List[OmsResponse] = field(default_factory=list)
    started_at_ns:  int           = 0
    finished_at_ns: int           = 0

    @property
    def qty_remaining(self) -> int:
        return self.config.total_qty - self.qty_filled

    @property
    def fill_rate(self) -> float:
        if self.config.total_qty == 0:
            return 0.0
        return self.qty_filled / self.config.total_qty

    @property
    def elapsed_sec(self) -> float:
        end = self.finished_at_ns or time.perf_counter_ns()
        return (end - self.started_at_ns) / 1e9 if self.started_at_ns else 0.0

    def is_done(self) -> bool:
        return self.state in (TwapState.Completed, TwapState.Cancelled)

    def summary(self) -> str:
        cfg = self.config
        return (
            f"TWAP #{cfg.parent_id} | {cfg.side.name} {cfg.total_qty} | "
            f"State={self.state.name} | "
            f"Slices={self.slices_sent}/{cfg.num_slices} | "
            f"Filled={self.qty_filled}/{cfg.total_qty} ({self.fill_rate:.1%}) | "
            f"AvgPx=${self.avg_fill_price / PRICE_MULT:.4f} | "
            f"Elapsed={self.elapsed_sec:.2f}s"
        )


class TwapExecutor:
    """
    Manages one or more TWAP jobs against a shared OMS.

    Usage (simulation — you drive the clock with .tick()):

        oms  = OrderManagementSystem(risk)
        exec = TwapExecutor(oms, next_order_id=5000)

        job_id = exec.create(TwapConfig(
            parent_id=1, side=Side.Buy,
            total_qty=1000, num_slices=10,
            limit_price=100_500,
        ))
        exec.start(job_id)

        for _ in range(10):          # simulate 10 time steps
            exec.tick(job_id)

        print(exec.status(job_id).summary())
    """

    def __init__(self, oms: OrderManagementSystem, next_order_id: int = 50_000) -> None:
        self._oms      = oms
        self._next_id  = next_order_id
        self._jobs:    dict[int, TwapStatus] = {}

    # ── Job lifecycle ─────────────────────────────────────────────────────────

    def create(self, cfg: TwapConfig) -> int:
        """Register a TWAP config. Returns *cfg.parent_id*."""
        self._jobs[cfg.parent_id] = TwapStatus(config=cfg)
        return cfg.parent_id

    def start(self, job_id: int) -> None:
        job = self._jobs[job_id]
        job.state         = TwapState.Running
        job.started_at_ns = time.perf_counter_ns()

    def cancel(self, job_id: int) -> None:
        job = self._jobs[job_id]
        job.state          = TwapState.Cancelled
        job.finished_at_ns = time.perf_counter_ns()

    def status(self, job_id: int) -> TwapStatus:
        return self._jobs[job_id]

    def all_jobs(self) -> List[TwapStatus]:
        return list(self._jobs.values())

    # ── Clock tick ────────────────────────────────────────────────────────────

    def tick(self, job_id: int) -> Optional[OmsResponse]:
        """
        Advance one time step for *job_id*.
        Submits the next child slice if the job is running and has slices left.
        Returns the OmsResponse for the child order, or None.
        """
        job = self._jobs.get(job_id)
        if job is None or job.state != TwapState.Running:
            return None
        if job.slices_sent >= job.config.num_slices:
            self._complete(job)
            return None

        cfg = job.config
        is_last_slice = (job.slices_sent == cfg.num_slices - 1)

        # Last slice gets the remainder so total qty is exact
        qty = cfg.slice_qty + (cfg.remainder_qty if is_last_slice else 0)
        if qty <= 0:
            self._complete(job)
            return None

        child_id   = self._next_id
        self._next_id += 1

        order_type = OrderType.Market if cfg.limit_price == 0 else OrderType.Limit
        resp = self._oms.submit(OrderRequest(
            id    = child_id,
            side  = cfg.side,
            type  = order_type,
            price = cfg.limit_price,
            qty   = qty,
        ))

        job.child_ids.append(child_id)
        job.responses.append(resp)
        job.slices_sent   += 1
        job.qty_submitted += qty

        # Accumulate fills
        for trade in resp.match_result.trades:
            filled_qty = trade.qty
            old_total  = job.qty_filled * job.avg_fill_price
            job.qty_filled     += filled_qty
            if job.qty_filled > 0:
                job.avg_fill_price = (old_total + trade.price * filled_qty) / job.qty_filled

        if job.slices_sent >= cfg.num_slices:
            self._complete(job)

        return resp

    def tick_all(self) -> List[OmsResponse]:
        """Advance all running jobs by one tick."""
        results = []
        for job_id in list(self._jobs):
            r = self.tick(job_id)
            if r:
                results.append(r)
        return results

    # ── Internal ──────────────────────────────────────────────────────────────

    def _complete(self, job: TwapStatus) -> None:
        job.state          = TwapState.Completed
        job.finished_at_ns = time.perf_counter_ns()
