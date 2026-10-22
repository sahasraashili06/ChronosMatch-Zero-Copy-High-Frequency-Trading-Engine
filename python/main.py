#!/usr/bin/env python3
"""
ChronosX -- HFT Matching Engine Simulator (Python)
Entry point: runs 5 demonstration scenarios then an SPSC throughput benchmark.
"""
import sys, io
# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


from chronosx import (
    Side, OrderType, OrderStatus, PRICE_MULT,
    RiskEngine, OrderManagementSystem, OrderRequest,
    Simulator, ScenarioEvent, EventKind,
)


def _fmt_price(ticks: int) -> str:
    return f"${ticks / PRICE_MULT:.4f}"


def _print_response(resp, prefix="  ") -> None:
    mr = resp.match_result
    if mr.reject_event:
        print(f"{prefix}REJECTED  id={resp.order_id}  reason={mr.reject_event.reason.name}")
        return
    print(f"{prefix}SUBMIT    id={resp.order_id}  → {mr.final_status.name}")
    for t in mr.trades:
        print(f"{prefix}  TRADE   agg={t.aggressor_id} rest={t.resting_id} "
              f"price={_fmt_price(t.price)} qty={t.qty}")
    if mr.cancel_event:
        ce = mr.cancel_event
        print(f"{prefix}  CANCEL  id={ce.order_id}  remaining={ce.remaining_qty} (IOC)")


def scenario_1(sim: Simulator) -> None:
    """Limit orders resting and matching — price-time priority."""
    print("\n── Scenario 1: Limit orders resting and matching ──")
    events = [
        ScenarioEvent(req=OrderRequest(id=1, side=Side.Buy,  type=OrderType.Limit, price=100_000, qty=50)),
        ScenarioEvent(req=OrderRequest(id=2, side=Side.Buy,  type=OrderType.Limit, price=100_000, qty=30)),
        ScenarioEvent(req=OrderRequest(id=3, side=Side.Buy,  type=OrderType.Limit, price=100_500, qty=10)),
        ScenarioEvent(req=OrderRequest(id=4, side=Side.Sell, type=OrderType.Limit, price=100_000, qty=100)),
    ]
    for r in sim.run_scenario(events):
        _print_response(r)


def scenario_2(sim: Simulator) -> None:
    """Market order IOC sweep."""
    print("\n── Scenario 2: Market order IOC sweep ──")
    events = [
        ScenarioEvent(req=OrderRequest(id=5, side=Side.Sell, type=OrderType.Limit,  price=101_000, qty=10)),
        ScenarioEvent(req=OrderRequest(id=6, side=Side.Buy,  type=OrderType.Market, price=0,       qty=200)),
    ]
    for r in sim.run_scenario(events):
        _print_response(r)


def scenario_3(sim: Simulator) -> None:
    """Pre-trade risk rejection."""
    print("\n── Scenario 3: Pre-trade risk rejection ──")
    events = [
        ScenarioEvent(req=OrderRequest(id=7, side=Side.Buy, type=OrderType.Limit, price=10_000, qty=99_999)),
    ]
    for r in sim.run_scenario(events):
        _print_response(r)


def scenario_4(sim: Simulator) -> None:
    """Order cancellation."""
    print("\n── Scenario 4: Order cancellation ──")
    events = [
        ScenarioEvent(req=OrderRequest(id=10, side=Side.Buy, type=OrderType.Limit, price=99_500, qty=100)),
        ScenarioEvent(kind=EventKind.Cancel, cancel_id=10),
    ]
    for r in sim.run_scenario(events):
        _print_response(r)
    sim.print_summary()


def scenario_5() -> None:
    """SPSC ring buffer throughput demo."""
    print("\n── Scenario 5: SPSC ring buffer throughput ──")
    sim = Simulator()
    num = 100_000
    rate = sim.run_spsc_demo(num)
    print(f"  Events  : {num:,}")
    print(f"  Rate    : ~{rate:,.0f} orders/sec")


def main() -> None:
    print("=" * 52)
    print("   ChronosX -- HFT Matching Engine Simulator")
    print("              Python Edition")
    print("=" * 52)

    sim = Simulator()
    scenario_1(sim)
    scenario_2(sim)
    scenario_3(sim)
    scenario_4(sim)
    scenario_5()


if __name__ == "__main__":
    main()
