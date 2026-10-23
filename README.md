# ChronosX — Zero-Copy HFT Matching Engine

> A from-scratch, cache-optimised **Python** limit order book and matching engine built for portfolio demonstration. Operates entirely in simulation mode — no live exchange connections.

[![CI](https://github.com/sahasraashili06/ChronosMatch-Zero-Copy-High-Frequency-Trading-Engine/actions/workflows/ci.yml/badge.svg)](https://github.com/sahasraashili06/ChronosMatch-Zero-Copy-High-Frequency-Trading-Engine/actions)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)

---

## Why This Project Exists

Most open-source matching engine tutorials make three silent assumptions that production systems cannot afford:

1. **Heap allocation is fine.** Every `new Order(...)` call invokes `malloc`, which can block for microseconds.
2. **Floating-point prices are fine.** `double` introduces IEEE 754 rounding — two "equal" prices can compare unequal.
3. **A mutex queue is fine.** Lock contention under load introduces kernel transitions and unbounded latency.

ChronosX eliminates all three — no heap on the hot path, no floating point, no locks between producer and consumer threads.

---

## Architecture at a Glance

```
┌──────────────────────────────────────────┐
│            Simulator / main.cpp          │  ← Scenario replay + SPSC demo
└──────────────────┬───────────────────────┘
                   │
     ┌─────────────▼──────────────┐
     │    OrderManagementSystem   │  ← ID assignment, validation, status tracking
     └──────┬───────────┬─────────┘
            │           │
  ┌─────────▼──┐  ┌─────▼──────────────┐
  │ RiskEngine │  │   MatchingEngine   │  ← Price-time priority FIFO
  │ qty+notional│  └────────┬───────────┘
  └────────────┘           │
                  ┌────────▼────────┐
                  │   OrderBook     │  ← std::map bid/ask + intrusive list
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │  ObjectPool<>   │  ← Pre-allocated, O(1) alloc/free
                  └─────────────────┘

  SpscRingBuffer<OrderRequest, N>    ← Producer ↔ Consumer, acquire-release
```

---

## Key Design Choices

| Decision | Rationale |
|---|---|
| `int64_t` tick prices | Eliminates floating-point rounding; exact equality in map keys |
| `ObjectPool<Order, N>` | Zero `malloc` after startup; contiguous memory = cache-friendly |
| Intrusive doubly-linked list | O(1) FIFO cancel without wrapper node allocations |
| `std::map` for price levels | O(log N_prices) with O(1) top-of-book; N_prices is typically small |
| SPSC ring buffer | Lock-free producer/consumer; no kernel transitions; acquire-release ordering |
| `alignas(64)` on `Order` | Each order occupies exactly one 64-byte cache line |
| Market orders = IOC | Unfilled residual is cancelled immediately, never rests |

---

## Project Structure

```
ChronosMatch-Zero-Copy-High-Frequency-Trading-Engine/
├── .github/workflows/ci.yml        # GCC-13 on Ubuntu + MSVC on Windows
├── cmake/
│   └── Dependencies.cmake          # FetchContent for GTest + Benchmark
├── docs/
│   ├── DESIGN.md                   # In-depth architecture rationale
│   └── REFERENCE_ANALYSIS.md       # Reference repo study & improvement notes
├── include/chronosx/
│   ├── types.hpp                   # Price (int64_t ticks), Quantity, enums, events
│   ├── order.hpp                   # Cache-line-aligned Order struct (64 bytes)
│   ├── memory_pool.hpp             # ObjectPool<T,N> — O(1) alloc/free, zero heap
│   ├── spsc_ring_buffer.hpp        # Lock-free SPSC queue (acquire-release)
│   ├── price_level.hpp             # Intrusive FIFO queue per price point
│   ├── order_book.hpp              # Limit Order Book interface
│   ├── matching_engine.hpp         # Core matching engine interface
│   ├── risk_engine.hpp             # Pre-trade risk: qty + notional limits
│   ├── oms.hpp                     # Order Management System interface
│   └── simulator.hpp               # Scenario replay + SPSC throughput demo
├── src/
│   ├── order_book.cpp
│   ├── matching_engine.cpp
│   ├── risk_engine.cpp
│   ├── oms.cpp
│   ├── simulator.cpp
│   └── main.cpp                    # Five demonstration scenarios
├── tests/
│   ├── test_types.cpp              # Fixed-point price, type layout asserts
│   ├── test_object_pool.cpp        # Pool alloc/free/exhaustion
│   ├── test_spsc_buffer.cpp        # Single and multi-threaded SPSC
│   ├── test_order_book.cpp         # Book add/cancel/best-price/spread
│   ├── test_matching_engine.cpp    # 20+ matching scenarios
│   ├── test_oms.cpp                # OMS lifecycle, validation, risk rejection
│   └── test_risk_engine.cpp        # Boundary + overflow tests
├── benchmarks/
│   └── bench_matching_engine.cpp   # 6 Google Benchmark scenarios
└── CMakeLists.txt
```

---

## Building

### Prerequisites

- **GCC 13+** or **Clang 16+** or **MSVC 2019+**
- **CMake 3.20+**
- Internet access on first build (FetchContent downloads GoogleTest + Benchmark)

### Quick Start (Linux / macOS)

```bash
git clone https://github.com/sahasraashili06/ChronosMatch-Zero-Copy-High-Frequency-Trading-Engine.git
cd ChronosMatch-Zero-Copy-High-Frequency-Trading-Engine

cmake -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DBUILD_BENCHMARKS=ON
cmake --build build -j$(nproc)

# Run all tests
ctest --test-dir build --output-on-failure -C Release
```

### Windows (PowerShell with WinLibs / MSVC)

```powershell
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release `
      -DBUILD_TESTING=ON -DBUILD_BENCHMARKS=ON
cmake --build build --config Release -j4
ctest --test-dir build --output-on-failure -C Release
```

### Run the Simulation

```bash
./build/chronosx_sim          # Linux
./build/Release/chronosx_sim.exe  # Windows
```

### Run Benchmarks

```bash
./build/chronosx_bench          # Linux
./build/Release/chronosx_bench.exe  # Windows
```

---

## Demo Output (Simulation)

```
╔══════════════════════════════════════════════════╗
║   ChronosX — HFT Matching Engine Simulator      ║
╚══════════════════════════════════════════════════╝

── Scenario 1: Limit orders resting and matching ──
  SUBMIT  id=1 BUY  LIMIT qty=50  @ $100.0000  → New
  SUBMIT  id=2 BUY  LIMIT qty=30  @ $100.0000  → New
  SUBMIT  id=3 BUY  LIMIT qty=10  @ $100.0500  → New
  SUBMIT  id=4 SELL LIMIT qty=100 @ $100.0000  → PartiallyFilled
   TRADE  agg=4 rest=3 price=$100.0500 qty=10
   TRADE  agg=4 rest=1 price=$100.0000 qty=50
   TRADE  agg=4 rest=2 price=$100.0000 qty=30
   RESIDUAL 10 lots resting at $100.0000

── Scenario 2: Market order IOC sweep ──
  SUBMIT  id=5 BUY MARKET qty=200  → PartiallyFilled
   TRADE  agg=5 rest=4 price=$100.0000 qty=10
   CANCEL order=5 residual=190 (IOC)

── Scenario 3: Pre-trade risk rejection ──
  SUBMIT  id=6 BUY LIMIT qty=99999 @ $1.0000  → Rejected (qty limit)

── Scenario 4: Order cancellation ──
  SUBMIT  id=10 BUY LIMIT qty=100 @ $99.5000  → New
  CANCEL  id=10  → Cancelled

── Scenario 5: SPSC ring buffer throughput ──
  Events  : 100,000
  Consumed: 100,000
  Rate    : ~2,500,000 orders/sec
```

---

## Benchmark Results (indicative)

Run `chronosx_bench` on your machine for actual numbers.

| Benchmark | What it measures |
|---|---|
| `BM_LimitOrderInsert` | Single resting limit order, no match |
| `BM_LimitOrderMatchOneToOne` | 1 sell vs 1 buy — exact fill |
| `BM_MarketOrderSweep10Levels` | Market buy sweeping 10 ask levels |
| `BM_CancelOrder` | O(1) cancel from a 1000-order book |
| `BM_ThroughputMixed` | Alternating buy/sell stream |
| `BM_OmsFullPipeline` | Full stack: validate → risk → match |

---

## Improvements Over Reference Patterns

| Area | Common pattern | ChronosX |
|---|---|---|
| Order memory | Heap (`new` / `shared_ptr`) | `ObjectPool` — zero malloc after init |
| Price type | `double` | `int64_t` ticks (4 decimal places) |
| Cancellation | O(N) linear scan | O(1) via price-index hash map |
| Risk checks | None | Qty + notional (overflow-safe `__int128`) |
| Thread comms | `mutex` + `queue` | Lock-free SPSC ring buffer |
| Cache layout | Ad-hoc structs | `alignas(64)` — one order per cache line |
| Test coverage | Happy path only | 50+ cases including edge cases |
| Benchmarks | Informal timings | 6 Google Benchmark scenarios |

---

## Safety Notice

This is an **educational simulator** only. It is not connected to any exchange, broker, or real-time market data feed. It must not be used as production trading infrastructure.

---

## Attribution

Inspired by the architectural concept of time-priority matching systems. The reference repository `https://github.com/ameetairodagi6-oss/chronosmatch-hft-engine` was inaccessible (HTTP 404) at development time. Architecture patterns were independently derived from published HFT engineering literature and open-source matching engines.

See [`docs/REFERENCE_ANALYSIS.md`](docs/REFERENCE_ANALYSIS.md) for the full analysis.

---

## License

MIT — see [`LICENSE`](LICENSE) for details.
## Development and Testing

ChronosMatch demonstrates order-book management, order matching, and trade execution in a simulated trading environment.

### Run Python Tests

From the project root, run:

    python -m pytest ./python/tests -v

This project is for educational purposes only and is not intended for live trading or financial advice.
