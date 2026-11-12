"""Tests for ReplayEngine and CSV parser"""
import io
import pytest
from chronosx.replay import ReplayEngine, parse_csv, ReplayEvent, ReplayStats
from chronosx.oms import OrderManagementSystem, OrderRequest
from chronosx.risk_engine import RiskEngine, RiskLimits
from chronosx.types import Side, OrderType, OrderStatus, PRICE_MULT


CSV_DATA = """\
ts_ns,order_id,side,type,price,qty
1000000,1,Sell,Limit,100000,50
2000000,2,Buy,Limit,100000,30
3000000,3,Buy,Market,0,10
4000000,4,Sell,Limit,101000,20
"""

BAD_QTY_CSV = """\
ts_ns,order_id,side,type,price,qty
1000,99,Buy,Limit,50000,999999999
"""


@pytest.fixture
def oms():
    limits = RiskLimits(max_order_qty=100_000, max_order_notional=10**15)
    return OrderManagementSystem(RiskEngine(limits))


@pytest.fixture
def engine(oms):
    return ReplayEngine(oms)


# ── Parser tests ──────────────────────────────────────────────────────────────

def test_parse_csv_count():
    events = parse_csv(io.StringIO(CSV_DATA))
    assert len(events) == 4


def test_parse_csv_sorted_by_ts():
    events = parse_csv(io.StringIO(CSV_DATA))
    ts_list = [e.ts_ns for e in events]
    assert ts_list == sorted(ts_list)


def test_parse_side_and_type():
    events = parse_csv(io.StringIO(CSV_DATA))
    assert events[0].side == Side.Sell
    assert events[0].type == OrderType.Limit
    assert events[2].type == OrderType.Market


def test_parse_default_symbol():
    events = parse_csv(io.StringIO(CSV_DATA))
    assert all(e.symbol == "DEFAULT" for e in events)


def test_parse_custom_symbol():
    csv = "ts_ns,order_id,side,type,price,qty,symbol\n1000,1,Buy,Limit,100000,10,AAPL\n"
    events = parse_csv(io.StringIO(csv))
    assert events[0].symbol == "AAPL"


# ── ReplayEngine tests ────────────────────────────────────────────────────────

def test_run_returns_stats(engine):
    events = parse_csv(io.StringIO(CSV_DATA))
    stats = engine.run(events)
    assert isinstance(stats, ReplayStats)
    assert stats.orders_submitted == 4


def test_run_empty_events(engine):
    stats = engine.run([])
    assert stats.orders_submitted == 0


def test_trades_recorded(engine):
    events = parse_csv(io.StringIO(CSV_DATA))
    stats = engine.run(events)
    # Order 1 (sell 50 @ 100000) crosses order 2 (buy 30) and order 3 (market 10)
    assert stats.trade_count >= 2
    assert stats.total_volume > 0


def test_vwap_computed(engine):
    events = parse_csv(io.StringIO(CSV_DATA))
    stats = engine.run(events)
    if stats.total_volume > 0:
        assert stats.vwap > 0.0


def test_on_trade_callback(oms):
    trades_seen = []
    eng = ReplayEngine(oms, on_trade=trades_seen.append)
    events = parse_csv(io.StringIO(CSV_DATA))
    eng.run(events)
    assert len(trades_seen) >= 1


def test_on_order_callback(oms):
    orders_seen = []
    eng = ReplayEngine(oms, on_order=orders_seen.append)
    events = parse_csv(io.StringIO(CSV_DATA))
    eng.run(events)
    assert len(orders_seen) == 4


def test_run_iter_yields_responses(engine):
    events = parse_csv(io.StringIO(CSV_DATA))
    responses = list(engine.run_iter(events))
    assert len(responses) == 4


def test_stats_string(engine):
    events = parse_csv(io.StringIO(CSV_DATA))
    stats = engine.run(events)
    s = str(stats)
    assert "submitted" in s
    assert "VWAP" in s
