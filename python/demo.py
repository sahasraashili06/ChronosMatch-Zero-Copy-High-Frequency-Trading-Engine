#!/usr/bin/env python3
"""
ChronosX -- Full-Stack Integration Demo

Demonstrates the complete trading system:
  1. OMS + RiskEngine + MatchingEngine
  2. MarketDataPublisher (book snapshots + trade reports)
  3. PositionManager (P&L tracking)
  4. MarketMaker strategy (inventory-aware quoting)
  5. SessionStats (VWAP, fill rate, spread)
  6. Order Book Visualizer (rich terminal display)

Run:  python demo.py
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from typing import List

from chronosx.types import Side, OrderType, OrderStatus, PRICE_MULT
from chronosx.risk_engine import RiskEngine, RiskLimits
from chronosx.oms import OrderManagementSystem, OrderRequest
from chronosx.market_data import MarketDataPublisher, BookSnapshot, TradeReport
from chronosx.position_manager import PositionManager
from chronosx.market_maker import MarketMaker, MMConfig
from chronosx.stats import SessionStats

try:
    from visualizer import render_book
    _VIZ = True
except ImportError:
    _VIZ = False


# ── Global state shared by callbacks ─────────────────────────────────────────
_last_snap:   BookSnapshot | None = None
_trade_tape:  List[TradeReport]   = []
_pm           = PositionManager()
_stats        = SessionStats()


def _on_book(snap: BookSnapshot) -> None:
    global _last_snap
    _last_snap = snap
    if snap.spread is not None:
        _stats.record_spread(snap.spread)


def _on_trade(report: TradeReport) -> None:
    _trade_tape.append(report)
    _pm.record_trade(
        _last_snap and __import__('chronosx.types', fromlist=['TradeEvent']),
        aggressor_side=report.aggressor_side,
    )
    _stats.record_trade(
        __import__('chronosx.types', fromlist=['TradeEvent']).TradeEvent(
            aggressor_id=report.aggressor_id,
            resting_id=report.resting_id,
            price=report.price,
            qty=report.qty,
        )
    )


def _submit(oms, pub, req: OrderRequest) -> None:
    """Submit an order and publish market data updates."""
    resp = oms.submit(req)
    mr   = resp.match_result
    _stats.record_order(
        submitted = True,
        filled    = mr.final_status == OrderStatus.Filled,
        partial   = mr.final_status == OrderStatus.PartiallyFilled,
        cancelled = mr.final_status == OrderStatus.Cancelled,
        rejected  = mr.final_status == OrderStatus.Rejected,
    )
    for trade in mr.trades:
        from chronosx.types import TradeEvent
        _trade_tape.append(TradeReport(
            instrument_id   = "SIM",
            seq             = 0,
            timestamp_ns    = 0,
            aggressor_id    = trade.aggressor_id,
            resting_id      = trade.resting_id,
            price           = trade.price,
            qty             = trade.qty,
            aggressor_side  = req.side,
        ))
        from chronosx.types import TradeEvent as TE
        _pm.record_trade(TE(
            aggressor_id=trade.aggressor_id,
            resting_id=trade.resting_id,
            price=trade.price,
            qty=trade.qty,
        ), aggressor_side=req.side)
        _stats.record_trade(trade)
    pub.on_order_event(oms.book, mr.trades, req.side)


def main() -> None:
    print("=" * 60)
    print("  ChronosX -- Full-Stack HFT Engine Demo (Python)")
    print("=" * 60)

    # ── Setup ─────────────────────────────────────────────────────────────────
    limits = RiskLimits(max_order_qty=5_000, max_order_notional=500_000_000_000)
    risk   = RiskEngine(limits)
    oms    = OrderManagementSystem(risk)
    pub    = MarketDataPublisher("CHRON", depth=8)
    mm_cfg = MMConfig(
        participant_id = 1,
        half_spread    = 100,
        order_qty      = 200,
        max_inventory  = 1000,
        requote_ticks  = 50,
    )
    mm = MarketMaker(oms, _pm, mm_cfg)

    pub.subscribe_book(_on_book)

    # ── Phase 1: Seed the book with resting orders ─────────────────────────
    print("\n[Phase 1] Seeding order book with resting limit orders...")
    ref = 100_000   # $10.0000 in ticks

    # Several sell levels
    for i, (price, qty) in enumerate([
        (ref + 100, 300), (ref + 200, 500), (ref + 300, 200),
        (ref + 400, 150), (ref + 500, 400),
    ], start=100):
        _submit(oms, pub, OrderRequest(id=i, side=Side.Sell,
                                       type=OrderType.Limit, price=price, qty=qty))

    # Several buy levels
    for i, (price, qty) in enumerate([
        (ref - 100, 250), (ref - 200, 400), (ref - 300, 300),
        (ref - 400, 100), (ref - 500, 350),
    ], start=200):
        _submit(oms, pub, OrderRequest(id=i, side=Side.Buy,
                                       type=OrderType.Limit, price=price, qty=qty))

    # ── Phase 2: Market maker seeds two-sided quotes ───────────────────────
    print("[Phase 2] Market maker placing two-sided quotes...")
    mm.seed_quotes(ref)
    pub.on_order_event(oms.book, [], Side.Buy)

    if _VIZ and _last_snap:
        render_book(_last_snap, _trade_tape)

    # ── Phase 3: Aggressive orders cross the spread ────────────────────────
    print("\n[Phase 3] Aggressive orders crossing the spread...")
    for i, (side, qty) in enumerate([
        (Side.Buy,  150),
        (Side.Sell, 200),
        (Side.Buy,  500),
        (Side.Sell, 100),
    ], start=300):
        price = ref + 500 if side == Side.Buy else ref - 500
        _submit(oms, pub, OrderRequest(id=i, side=side,
                                       type=OrderType.Limit, price=price, qty=qty))

    if _VIZ and _last_snap:
        render_book(_last_snap, _trade_tape)

    # ── Phase 4: Market order IOC sweep ───────────────────────────────────
    print("[Phase 4] Market order IOC sweep (buy 800)...")
    resp = oms.submit(OrderRequest(id=400, side=Side.Buy,
                                   type=OrderType.Market, price=0, qty=800))
    for trade in resp.match_result.trades:
        _stats.record_trade(trade)
    pub.on_order_event(oms.book, resp.match_result.trades, Side.Buy)

    if _VIZ and _last_snap:
        render_book(_last_snap, _trade_tape)

    # ── Phase 5: Cancel MM quotes ──────────────────────────────────────────
    print("[Phase 5] Market maker cancelling quotes...")
    mm.cancel_all()
    pub.on_order_event(oms.book, [], Side.Buy)

    # ── Reports ────────────────────────────────────────────────────────────
    mark_price = ref + 50
    _pm.print_summary(mark_price)
    _stats.print_report()
    print(f"\n  {mm.status()}")
    print()


if __name__ == "__main__":
    main()
