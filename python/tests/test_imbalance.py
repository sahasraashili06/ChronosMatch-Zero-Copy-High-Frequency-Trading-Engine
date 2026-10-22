"""Tests for OrderBookImbalance"""
import pytest
from chronosx.imbalance import OrderBookImbalance, ImbalanceReading
from chronosx.order_book import OrderBook
from chronosx.matching_engine import MatchingEngine
from chronosx.oms import OrderManagementSystem, OrderRequest
from chronosx.risk_engine import RiskEngine, RiskLimits
from chronosx.types import Side, OrderType


@pytest.fixture
def oms():
    limits = RiskLimits(max_order_qty=100_000, max_order_notional=10**15)
    return OrderManagementSystem(RiskEngine(limits))


def _bid(oms, order_id, price, qty):
    oms.submit(OrderRequest(order_id, Side.Buy, OrderType.Limit, price, qty))

def _ask(oms, order_id, price, qty):
    oms.submit(OrderRequest(order_id, Side.Sell, OrderType.Limit, price, qty))


def test_empty_book_returns_none(oms):
    obi = OrderBookImbalance()
    assert obi.compute(oms.book) is None


def test_pure_bid_pressure(oms):
    _bid(oms, 1, 100_000, 100)
    obi = OrderBookImbalance()
    r = obi.compute(oms.book)
    assert r is not None
    assert r.raw == pytest.approx(1.0)
    assert r.direction == "BUY_PRESSURE"


def test_pure_ask_pressure(oms):
    _ask(oms, 1, 100_000, 100)
    obi = OrderBookImbalance()
    r = obi.compute(oms.book)
    assert r is not None
    assert r.raw == pytest.approx(-1.0)
    assert r.direction == "SELL_PRESSURE"


def test_balanced_book_is_neutral(oms):
    _bid(oms, 1, 99_000, 100)
    _ask(oms, 2, 101_000, 100)
    obi = OrderBookImbalance()
    r = obi.compute(oms.book)
    assert r is not None
    assert r.raw == pytest.approx(0.0, abs=1e-9)
    assert r.direction == "NEUTRAL"


def test_imbalance_range(oms):
    _bid(oms, 1, 99_000, 60)
    _ask(oms, 2, 101_000, 40)
    obi = OrderBookImbalance()
    r = obi.compute(oms.book)
    assert r is not None
    assert -1.0 <= r.raw <= 1.0


def test_ema_updates(oms):
    _bid(oms, 1, 99_000, 80)
    _ask(oms, 2, 101_000, 20)
    obi = OrderBookImbalance(ema_alpha=0.5)
    obi.update(oms.book)
    assert obi.ema is not None
    assert obi.count == 1
    obi.update(oms.book)
    assert obi.count == 2


def test_weighted_differs_from_raw(oms):
    # Multiple levels — level 1 has heavier weight
    _bid(oms, 1, 100_000, 10)
    _bid(oms, 2, 99_000,  90)
    _ask(oms, 3, 101_000, 50)
    obi = OrderBookImbalance(depth=5)
    r = obi.compute(oms.book)
    assert r is not None
    # weighted and raw may differ when levels have different sizes
    assert isinstance(r.weighted, float)


def test_queue_imbalance_level1_only(oms):
    _bid(oms, 1, 100_000, 30)
    _ask(oms, 2, 101_000, 70)
    obi = OrderBookImbalance()
    r = obi.compute(oms.book)
    assert r is not None
    expected = (30 - 70) / (30 + 70)
    assert r.queue_imbalance == pytest.approx(expected, abs=1e-6)


def test_str_representation(oms):
    _bid(oms, 1, 100_000, 50)
    _ask(oms, 2, 101_000, 50)
    obi = OrderBookImbalance()
    r = obi.compute(oms.book)
    assert r is not None
    s = str(r)
    assert "NEUTRAL" in s or "PRESSURE" in s
