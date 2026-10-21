"""
ChronosX -- Latency Profiler

Measures end-to-end order processing latency with nanosecond precision.
Reports p50, p95, p99, p99.9, min, max, and mean.

In HFT, every microsecond counts. This module lets you profile:
- Submit latency  : time from request to MatchResult
- Match latency   : time spent inside the matching loop
- Full OMS latency: risk check + match + event dispatch
"""
from __future__ import annotations

import time
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from contextlib import contextmanager


@dataclass
class LatencyStats:
    """Percentile summary of a latency sample set."""
    name:     str
    count:    int
    mean_ns:  float
    min_ns:   int
    max_ns:   int
    p50_ns:   float
    p95_ns:   float
    p99_ns:   float
    p999_ns:  float

    def _fmt(self, ns: float) -> str:
        if ns < 1_000:
            return f"{ns:.1f} ns"
        elif ns < 1_000_000:
            return f"{ns/1_000:.2f} us"
        else:
            return f"{ns/1_000_000:.3f} ms"

    def __str__(self) -> str:
        return (
            f"[{self.name}]  n={self.count:,}\n"
            f"  mean={self._fmt(self.mean_ns)}  "
            f"min={self._fmt(self.min_ns)}  "
            f"max={self._fmt(self.max_ns)}\n"
            f"  p50={self._fmt(self.p50_ns)}  "
            f"p95={self._fmt(self.p95_ns)}  "
            f"p99={self._fmt(self.p99_ns)}  "
            f"p99.9={self._fmt(self.p999_ns)}"
        )


class LatencyProfiler:
    """
    Records nanosecond latency samples per named operation.

    Usage:
        prof = LatencyProfiler()

        with prof.measure("submit"):
            engine.submit_limit(...)

        # Or manually:
        t0 = prof.start()
        engine.submit_limit(...)
        prof.record("submit", t0)

        print(prof.report("submit"))
    """

    def __init__(self) -> None:
        self._samples: Dict[str, List[int]] = {}

    # ── Context manager ───────────────────────────────────────────────────────

    @contextmanager
    def measure(self, name: str):
        t0 = time.perf_counter_ns()
        try:
            yield
        finally:
            self._store(name, time.perf_counter_ns() - t0)

    # ── Manual API ────────────────────────────────────────────────────────────

    def start(self) -> int:
        return time.perf_counter_ns()

    def record(self, name: str, start_ns: int) -> int:
        elapsed = time.perf_counter_ns() - start_ns
        self._store(name, elapsed)
        return elapsed

    def add_sample(self, name: str, elapsed_ns: int) -> None:
        self._store(name, elapsed_ns)

    # ── Queries ───────────────────────────────────────────────────────────────

    def sample_count(self, name: str) -> int:
        return len(self._samples.get(name, []))

    def all_names(self) -> List[str]:
        return list(self._samples.keys())

    def percentile(self, name: str, pct: float) -> Optional[float]:
        """Return *pct*-th percentile (0–100) for *name*, or None."""
        s = self._samples.get(name)
        if not s:
            return None
        sorted_s = sorted(s)
        idx = (pct / 100) * (len(sorted_s) - 1)
        lo, hi = int(idx), min(int(idx) + 1, len(sorted_s) - 1)
        frac = idx - lo
        return sorted_s[lo] * (1 - frac) + sorted_s[hi] * frac

    def stats(self, name: str) -> Optional[LatencyStats]:
        s = self._samples.get(name)
        if not s:
            return None
        return LatencyStats(
            name    = name,
            count   = len(s),
            mean_ns = statistics.mean(s),
            min_ns  = min(s),
            max_ns  = max(s),
            p50_ns  = self.percentile(name, 50)  or 0,
            p95_ns  = self.percentile(name, 95)  or 0,
            p99_ns  = self.percentile(name, 99)  or 0,
            p999_ns = self.percentile(name, 99.9) or 0,
        )

    def report(self, name: str) -> str:
        st = self.stats(name)
        return str(st) if st else f"[{name}] no samples recorded"

    def print_all(self) -> None:
        print("\n=== Latency Report ===")
        for name in sorted(self._samples):
            print(self.report(name))
            print()

    def reset(self, name: Optional[str] = None) -> None:
        if name:
            self._samples.pop(name, None)
        else:
            self._samples.clear()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _store(self, name: str, elapsed_ns: int) -> None:
        if name not in self._samples:
            self._samples[name] = []
        self._samples[name].append(elapsed_ns)
