# ChronosMatch mmap Ring Buffer Benchmark

## Overview

This benchmark measures the performance of the memory-mapped ring buffer used in ChronosMatch.

It measures:
- Push and pop throughput.
- Average push-plus-pop latency.
- Median latency (P50).
- P95 latency.
- P99 latency.

## Requirements

Install the project dependencies:

```bash
python -m pip install -r python/requirements.txt
```

## Run

From the repository root:

```bash
python python/benchmarks/bench_mmap_ring_buffer.py
```

## Workloads

The benchmark tests:
- 10,000 orders
- 100,000 orders
- 1,000,000 orders

## Sample Debian Results

Five-run average for the 1,000,000-order workload:

| Metric | Result |
|---|---:|
| Throughput | 557,139 orders/sec |
| Average push + pop latency | 1,812 ns |

These are sample measurements from one Debian environment, not guaranteed performance figures.

## Important Notes

- The benchmark runs push and pop sequentially in one process.
- It uses a multiprocessing lock.
- Latency includes Python timing and function-call overhead.
- It does not measure lock-free or hardware-level latency.
- Results may vary with CPU load, operating system and hardware.

The multiprocessing producer-consumer demo is a separate measurement and should not be directly compared with this single-process benchmark.
