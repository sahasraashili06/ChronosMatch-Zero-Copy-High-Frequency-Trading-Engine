/**
 * @file bench_matching_engine.cpp
 * @brief Google Benchmark microbenchmark suite for ChronosX.
 *
 * Build in Release mode for meaningful numbers:
 *   cmake -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_BENCHMARKS=ON
 *   cmake --build build --config Release -j4
 *   ./build/Release/chronosx_bench   (Windows)
 *   ./build/chronosx_bench           (Linux)
 */

#include <benchmark/benchmark.h>
#include "chronosx/matching_engine.hpp"
#include "chronosx/oms.hpp"
#include "chronosx/risk_engine.hpp"

using namespace chronosx;

// ============================================================
// BM_LimitOrderInsert
// A single limit buy with no counterpart, just resting.
// ============================================================
static void BM_LimitOrderInsert(benchmark::State& state) {
    MatchingEngine engine;
    OrderId id = 1;

    for (auto _ : state) {
        benchmark::DoNotOptimize(
            engine.submit_limit(id++, Side::Buy, 100'000, 10)
        );
    }
    state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
}
BENCHMARK(BM_LimitOrderInsert);

// ============================================================
// BM_LimitOrderMatchOneToOne
// Fresh engine per iteration: 1 resting sell vs 1 aggressive buy.
// ============================================================
static void BM_LimitOrderMatchOneToOne(benchmark::State& state) {
    for (auto _ : state) {
        MatchingEngine engine;
        (void)engine.submit_limit(1, Side::Sell, 100'000, 100);
        benchmark::DoNotOptimize(
            engine.submit_limit(2, Side::Buy, 100'000, 100)
        );
    }
    state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
}
BENCHMARK(BM_LimitOrderMatchOneToOne);

// ============================================================
// BM_MarketOrderSweep10Levels
// Market buy sweeping a book pre-loaded with 10 distinct ask levels.
// ============================================================
static void BM_MarketOrderSweep10Levels(benchmark::State& state) {
    for (auto _ : state) {
        state.PauseTiming();
        MatchingEngine engine;
        for (int i = 0; i < 10; ++i) {
            (void)engine.submit_limit(
                static_cast<OrderId>(i + 1),
                Side::Sell,
                static_cast<Price>(100'000 + i * 100),
                10
            );
        }
        state.ResumeTiming();

        benchmark::DoNotOptimize(
            engine.submit_market(100, Side::Buy, 100)
        );
    }
    state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
}
BENCHMARK(BM_MarketOrderSweep10Levels);

// ============================================================
// BM_CancelOrder
// Cancel a resting order from a book with 1000 orders.
// ============================================================
static void BM_CancelOrder(benchmark::State& state) {
    constexpr int kOrders = 1000;
    MatchingEngine engine;

    // Pre-populate with buy orders at different prices
    for (int i = 0; i < kOrders; ++i) {
        (void)engine.submit_limit(
            static_cast<OrderId>(i + 1),
            Side::Buy,
            static_cast<Price>(100'000 - i),
            10
        );
    }

    OrderId id_to_cancel = 1;

    for (auto _ : state) {
        if (id_to_cancel > kOrders) {
            state.SkipWithError("Ran out of orders to cancel");
            break;
        }
        benchmark::DoNotOptimize(
            engine.cancel_order(id_to_cancel++)
        );
    }
    state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
}
BENCHMARK(BM_CancelOrder);

// ============================================================
// BM_ThroughputMixed
// Sustained alternating buy/sell stream on a single instrument.
// Reports orders/sec throughput.
// ============================================================
static void BM_ThroughputMixed(benchmark::State& state) {
    MatchingEngine engine;
    OrderId id = 1;

    for (auto _ : state) {
        if (id % 2 == 0) {
            benchmark::DoNotOptimize(
                engine.submit_limit(id, Side::Buy, 99'000 + static_cast<Price>(id % 1000), 1)
            );
        } else {
            benchmark::DoNotOptimize(
                engine.submit_limit(id, Side::Sell, 101'000 - static_cast<Price>(id % 1000), 1)
            );
        }
        ++id;
    }

    state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
}
BENCHMARK(BM_ThroughputMixed);

// ============================================================
// BM_OmsFullPipeline
// Full OMS pipeline: validate → risk → match.
// ============================================================
static void BM_OmsFullPipeline(benchmark::State& state) {
    RiskEngine risk{RiskLimits{
        .max_order_qty      = 10'000,
        .max_order_notional = 10'000'000'000LL,
    }};
    OrderManagementSystem oms{risk};
    OrderId id = 1;

    for (auto _ : state) {
        benchmark::DoNotOptimize(
            oms.submit({
                .id    = id++,
                .side  = Side::Buy,
                .type  = OrderType::Limit,
                .price = 100'000,
                .qty   = 10,
            })
        );
    }
    state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
}
BENCHMARK(BM_OmsFullPipeline);
