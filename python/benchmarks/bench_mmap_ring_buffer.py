#!/usr/bin/env python3
"""ChronosMatch mmap ring buffer performance benchmark."""

import multiprocessing
import os
import statistics
import tempfile
import time

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1])
)

from chronosx.mmap_ring_buffer import MmapRingBuffer

CAPACITY = 4096
WORKLOADS = [10_000, 100_000, 1_000_000]
LATENCY_SAMPLES = 10_000


def percentile(values, percent):
    values = sorted(values)
    index = int((len(values) - 1) * percent / 100)
    return values[index]


def run_benchmark(total_orders):
    fd, path = tempfile.mkstemp(prefix="chronos_bench_")
    os.close(fd)

    lock = multiprocessing.Lock()
    buffer = MmapRingBuffer(path, CAPACITY, lock, create=True)

    try:
        # Throughput measurement
        start = time.perf_counter()

        for order_id in range(1, total_orders + 1):
            side = 1 if order_id % 2 else -1

            if not buffer.push(order_id, side, 100_000, 10):
                raise RuntimeError("Buffer unexpectedly full")

            order = buffer.pop()

            if order is None or order["order_id"] != order_id:
                raise RuntimeError("Order verification failed")

        elapsed = time.perf_counter() - start
        throughput = total_orders / elapsed

        # Individual push + pop latency measurement
        latencies = []

        for order_id in range(1, LATENCY_SAMPLES + 1):
            start_ns = time.perf_counter_ns()

            buffer.push(order_id, 1, 100_000, 10)
            order = buffer.pop()

            end_ns = time.perf_counter_ns()

            if order is None or order["order_id"] != order_id:
                raise RuntimeError("Latency test verification failed")

            latencies.append(end_ns - start_ns)

        print(f"\nWorkload: {total_orders:,} orders")
        print(f"Elapsed time: {elapsed:.4f} seconds")
        print(f"Throughput: {throughput:,.0f} orders/sec")
        print(
            f"Average push+pop latency: "
            f"{statistics.mean(latencies):,.0f} ns"
        )
        print(
            f"Median latency: "
            f"{statistics.median(latencies):,.0f} ns"
        )
        print(f"P95 latency: {percentile(latencies, 95):,.0f} ns")
        print(f"P99 latency: {percentile(latencies, 99):,.0f} ns")

    finally:
        buffer.close()
        os.unlink(path)


if __name__ == "__main__":
    print("=== ChronosMatch mmap Ring Buffer Benchmark ===")

    for workload in WORKLOADS:
        run_benchmark(workload)
