"""
ChronosX -- Latency Profiler

Measures and tracks order-to-fill round-trip latency in nanoseconds.
Critical for HFT where microseconds determine profitability.

Tracks per-event timings using time.perf_counter_ns() and computes:
  - Min / Max / Mean latency
  - P50 / P95 / P99 percentiles (sorted-insert, no numpy)
  - Slowdown alerts when a sample exceeds N x mean

Usage:
    prof = LatencyProfiler(alert_multiplier=5.0)

    t0 = prof.start("order_123")
    # ... send order to exchange ...
    sample = prof.stop("order_123")

    print(f"Round-trip: {sample.latency_us:.1f} us")
    print(prof.summary())
"""
from __future__ import annotations

import bisect
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class LatencySample:
    event_id:   str
    start_ns:   int
    end_ns:     int

    @property
    def latency_ns(self) -> int:
        return self.end_ns - self.start_ns

    @property
    def latency_us(self) -> float:
        return self.latency_ns / 1_000.0

    @property
    def latency_ms(self) -> float:
        return self.latency_ns / 1_000_000.0

    def __str__(self) -> str:
        return f"LatencySample[{self.event_id}] {self.latency_us:.2f} us"


@dataclass
class LatencyStats:
    count:   int
    min_ns:  int
    max_ns:  int
    mean_ns: float
    p50_ns:  int
    p95_ns:  int
    p99_ns:  int

    @property
    def mean_us(self) -> float: return self.mean_ns / 1_000.0

    @property
    def p50_us(self) -> float:  return self.p50_ns  / 1_000.0

    @property
    def p95_us(self) -> float:  return self.p95_ns  / 1_000.0

    @property
    def p99_us(self) -> float:  return self.p99_ns  / 1_000.0

    @property
    def min_us(self) -> float:  return self.min_ns  / 1_000.0

    @property
    def max_us(self) -> float:  return self.max_ns  / 1_000.0

    def __str__(self) -> str:
        return (
            f"Latency[n={self.count}]  "
            f"min={self.min_us:.1f}us  "
            f"mean={self.mean_us:.1f}us  "
            f"p50={self.p50_us:.1f}us  "
            f"p95={self.p95_us:.1f}us  "
            f"p99={self.p99_us:.1f}us  "
            f"max={self.max_us:.1f}us"
        )


class LatencyProfiler:
    """
    Nanosecond-precision latency tracker using perf_counter_ns.

    Args:
        alert_multiplier: Fire a slow-path alert when latency > N x mean.
        max_samples:      Rolling window size (older samples dropped).
    """

    def __init__(
        self,
        alert_multiplier: float = 5.0,
        max_samples:      int   = 10_000,
    ) -> None:
        if alert_multiplier <= 0:
            raise ValueError("alert_multiplier must be positive")
        self._multiplier  = alert_multiplier
        self._max_samples = max_samples
        self._pending:    Dict[str, int] = {}
        self._samples:    List[LatencySample] = []
        self._sorted:     List[int] = []
        self._total_ns:   int = 0
        self._alerts:     List[LatencySample] = []

    # ---- Timing API ----------------------------------------------------------

    def start(self, event_id: str) -> int:
        """Mark the start of an event. Returns start timestamp (ns)."""
        ts = time.perf_counter_ns()
        self._pending[event_id] = ts
        return ts

    def stop(self, event_id: str) -> Optional[LatencySample]:
        """
        Mark the end of an event. Returns a LatencySample, or None
        if start() was never called for this event_id.
        """
        ts = time.perf_counter_ns()
        start = self._pending.pop(event_id, None)
        if start is None:
            return None
        sample = LatencySample(event_id=event_id, start_ns=start, end_ns=ts)
        self._record(sample)
        return sample

    def record_ns(self, event_id: str, latency_ns: int) -> LatencySample:
        """Directly record a known latency value (e.g. from hardware timestamps)."""
        now = time.perf_counter_ns()
        sample = LatencySample(
            event_id=event_id,
            start_ns=now - latency_ns,
            end_ns=now,
        )
        self._record(sample)
        return sample

    # ---- Stats ---------------------------------------------------------------

    def stats(self) -> Optional[LatencyStats]:
        """Returns statistics, or None if no samples recorded yet."""
        if not self._sorted:
            return None
        n = len(self._sorted)
        return LatencyStats(
            count   = n,
            min_ns  = self._sorted[0],
            max_ns  = self._sorted[-1],
            mean_ns = self._total_ns / n,
            p50_ns  = self._percentile(50),
            p95_ns  = self._percentile(95),
            p99_ns  = self._percentile(99),
        )

    def summary(self) -> str:
        st = self.stats()
        return str(st) if st else "LatencyProfiler: no samples yet"

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    @property
    def alert_count(self) -> int:
        return len(self._alerts)

    @property
    def alerts(self) -> List[LatencySample]:
        return list(self._alerts)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def reset(self) -> None:
        self._pending.clear()
        self._samples.clear()
        self._sorted.clear()
        self._total_ns = 0
        self._alerts.clear()

    # ---- Internal ------------------------------------------------------------

    def _record(self, sample: LatencySample) -> None:
        lat = sample.latency_ns

        # Rolling window eviction
        if len(self._samples) >= self._max_samples:
            evicted = self._samples.pop(0)
            idx = bisect.bisect_left(self._sorted, evicted.latency_ns)
            if idx < len(self._sorted):
                self._sorted.pop(idx)
            self._total_ns -= evicted.latency_ns

        self._samples.append(sample)
        bisect.insort(self._sorted, lat)
        self._total_ns += lat

        # Slow-path alert
        n = len(self._sorted)
        mean = self._total_ns / n
        if n >= 5 and lat > self._multiplier * mean:
            self._alerts.append(sample)

    def _percentile(self, pct: int) -> int:
        n = len(self._sorted)
        if n == 0:
            return 0
        idx = min(int(n * pct / 100), n - 1)
        return self._sorted[idx]
