#!/usr/bin/env python3
"""
ChronosX -- Python Benchmarks
Measures throughput for key operations using timeit.
Run: python benchmarks/bench_matching_engine.py
"""
import sys, io
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import timeit
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chronosx.matching_engine import MatchingEngine
from chronosx.types import Side, OrderStatus, OrderType
from chronosx.oms import OrderManagementSystem, OrderRequest
from chronosx.risk_engine import RiskEngine

# Small pool — fast to construct, avoids O(N) allocation overhead in loops
SMALL_POOL = 4096
ITERATIONS = 50_000


def bench_limit_insert():
    """Single resting limit orders, no match."""
    def run():
        engine = MatchingEngine(SMALL_POOL)
        for i in range(1, SMALL_POOL):          # stay within pool
            engine.submit_limit(i, Side.Buy, 100_000, 10)
    t = timeit.timeit(run, number=10)
    rate = (SMALL_POOL * 10) / t
    print(f"  BM_LimitOrderInsert         {rate:>12,.0f} orders/sec  ({t*100:.1f} ms/iter)")


def bench_one_to_one_match():
    """1 sell vs 1 buy -- exact fill each round."""
    rounds = 2000
    def run():
        engine = MatchingEngine(SMALL_POOL)
        for i in range(0, rounds * 2, 2):
            engine.submit_limit(i + 1, Side.Sell, 100_000, 100)
            engine.submit_limit(i + 2, Side.Buy,  100_000, 100)
    t = timeit.timeit(run, number=10)
    rate = (rounds * 2 * 10) / t
    print(f"  BM_LimitOrderMatchOneToOne  {rate:>12,.0f} orders/sec  ({t*100:.1f} ms/iter)")


def bench_market_sweep_10_levels():
    """Market buy sweeping 10 ask levels, reuse one engine."""
    rounds = 500
    def run():
        engine = MatchingEngine(SMALL_POOL)
        oid = 1
        for _ in range(rounds):
            for j in range(10):
                engine.submit_limit(oid, Side.Sell, 100_000 + j * 100, 10)
                oid += 1
            engine.submit_market(oid, Side.Buy, 100)
            oid += 1
    t = timeit.timeit(run, number=5)
    rate = (rounds * 5) / t
    print(f"  BM_MarketOrderSweep10Lvls   {rate:>12,.0f} sweeps/sec  ({t*200:.1f} ms/iter)")


def bench_cancel():
    """O(1) cancel from a live book."""
    n = 1000
    def run():
        engine = MatchingEngine(SMALL_POOL)
        for i in range(1, n + 1):
            engine.submit_limit(i, Side.Buy, 100_000 - i, 10)
        for i in range(1, n + 1):
            engine.cancel_order(i)
    t = timeit.timeit(run, number=20)
    rate = (n * 20) / (t / 2)   # divide by 2: half time is insert, half cancel
    print(f"  BM_CancelOrder              {rate:>12,.0f} cancels/sec ({t*50:.1f} ms/iter)")


def bench_oms_full_pipeline():
    """Full stack: validate -> risk -> match."""
    risk  = RiskEngine()
    rounds = 1000
    def run():
        oms = OrderManagementSystem(risk)
        for i in range(0, rounds * 2, 2):
            oms.submit(OrderRequest(i+1, Side.Sell, OrderType.Limit, 100_000, 10))
            oms.submit(OrderRequest(i+2, Side.Buy,  OrderType.Limit, 100_000, 10))
    t = timeit.timeit(run, number=10)
    rate = (rounds * 2 * 10) / t
    print(f"  BM_OmsFullPipeline          {rate:>12,.0f} orders/sec  ({t*100:.1f} ms/iter)")


if __name__ == "__main__":
    print("\n=== ChronosX Python Benchmarks ===")
    print(f"  Pool capacity per benchmark: {SMALL_POOL:,}\n")
    bench_limit_insert()
    bench_one_to_one_match()
    bench_market_sweep_10_levels()
    bench_cancel()
    bench_oms_full_pipeline()
    print()
