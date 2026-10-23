#include "chronosx/simulator.hpp"
#include "chronosx/spsc_ring_buffer.hpp"

#include <iostream>
#include <iomanip>
#include <chrono>
#include <thread>
#include <atomic>

namespace chronosx {

// ============================================================
// Constructor
// ============================================================
Simulator::Simulator()
    : risk_()
    , oms_(risk_)
{}

// ============================================================
// run_scenario — synchronous replay
// ============================================================
std::vector<OmsResponse> Simulator::run_scenario(const std::vector<ScenarioEvent>& events) {
    std::vector<OmsResponse> results;
    results.reserve(events.size());

    for (const auto& ev : events) {
        if (ev.kind == ScenarioEvent::Kind::NewOrder) {
            results.push_back(oms_.submit(ev.req));
        } else {
            results.push_back(oms_.cancel(ev.cancel_id));
        }
    }
    return results;
}

// ============================================================
// run_spsc_demo — producer/consumer thread pair
// ============================================================
double Simulator::run_spsc_demo(std::size_t num_events) {
    SpscRingBuffer<OrderRequest, kSimRingCapacity> ring;
    std::atomic<bool> done{false};

    // Reset the OMS/engine for a clean run
    RiskEngine  fresh_risk;
    OrderManagementSystem fresh_oms(fresh_risk);

    std::size_t produced = 0;
    std::size_t consumed = 0;

    const auto t_start = std::chrono::high_resolution_clock::now();

    // Producer thread
    std::thread producer([&]() {
        OrderId id = 1;
        for (std::size_t i = 0; i < num_events; ++i) {
            OrderRequest req{
                .id    = id++,
                .side  = (i % 2 == 0) ? Side::Buy : Side::Sell,
                .type  = OrderType::Limit,
                .price = 100'000 + static_cast<Price>(i % 100),  // ticks
                .qty   = 10,
            };
            // Spin-wait if ring is full
            while (!ring.push(req)) {
                // busy-spin
            }
            ++produced;
        }
        done.store(true, std::memory_order_release);
    });

    // Consumer loop (main thread)
    OrderRequest req{};
    while (!done.load(std::memory_order_acquire) || !ring.empty()) {
        if (ring.pop(req)) {
            (void)fresh_oms.submit(req);
            ++consumed;
        }
    }
    // Drain any final items
    while (ring.pop(req)) {
        (void)fresh_oms.submit(req);
        ++consumed;
    }

    const auto t_end = std::chrono::high_resolution_clock::now();
    producer.join();

    const double elapsed_s =
        std::chrono::duration<double>(t_end - t_start).count();

    return static_cast<double>(consumed) / elapsed_s;
}

// ============================================================
// print_summary
// ============================================================
void Simulator::print_summary(std::ostream& out) const {
    const auto& book = oms_.book();
    out << "\n=== ChronosX Simulator Summary ===\n";
    out << "  Total orders tracked : " << oms_.order_count()   << "\n";
    out << "  Active book orders   : " << book.active_order_count() << "\n";
    out << "  Bid levels           : " << book.bid_levels()    << "\n";
    out << "  Ask levels           : " << book.ask_levels()    << "\n";

    auto bb = book.best_bid();
    auto ba = book.best_ask();
    out << "  Best bid             : ";
    if (bb) out << *bb << " ticks ($" << std::fixed << std::setprecision(4)
                << static_cast<double>(*bb) / kPriceMult << ")\n";
    else    out << "N/A\n";

    out << "  Best ask             : ";
    if (ba) out << *ba << " ticks ($" << std::fixed << std::setprecision(4)
                << static_cast<double>(*ba) / kPriceMult << ")\n";
    else    out << "N/A\n";

    auto sp = book.spread();
    out << "  Spread               : ";
    if (sp) out << *sp << " ticks\n";
    else    out << "N/A\n";
}

// ============================================================
// print_book
// ============================================================
void Simulator::print_book(std::ostream& out) const {
    const auto& b = oms_.book();
    out << "\n--- Order Book (top 5 levels) ---\n";
    out << std::setw(12) << "Bid Qty"
        << std::setw(14) << "Price (ticks)"
        << std::setw(12) << "Ask Qty" << "\n";
    out << std::string(38, '-') << "\n";

    // We can't iterate bids/asks directly (private), but we can check levels
    // by constructing a range. For now we print best bid/ask.
    auto bb = b.best_bid();
    auto ba = b.best_ask();

    if (bb) {
        out << std::setw(12) << b.bid_qty_at(*bb)
            << std::setw(14) << *bb
            << std::setw(12) << "" << "\n";
    }
    if (ba) {
        out << std::setw(12) << ""
            << std::setw(14) << *ba
            << std::setw(12) << b.ask_qty_at(*ba) << "\n";
    }
}

// ============================================================
// book accessor
// ============================================================
const OrderBook& Simulator::book() const noexcept {
    return oms_.book();
}

} // namespace chronosx
