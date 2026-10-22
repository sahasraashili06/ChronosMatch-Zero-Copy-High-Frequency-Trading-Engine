"""Tests for MatchingEngine — 20+ scenarios"""
import pytest
from chronosx.matching_engine import MatchingEngine
from chronosx.types import Side, OrderStatus


@pytest.fixture
def engine():
    return MatchingEngine()


# ── No match ─────────────────────────────────────────────────────────────────

def test_limit_buy_rests_when_no_ask(engine):
    r = engine.submit_limit(1, Side.Buy, 1000, 10)
    assert r.trades == []
    assert r.final_status == OrderStatus.New
    assert engine.book.best_bid() == 1000


def test_limit_sell_rests_when_no_bid(engine):
    r = engine.submit_limit(1, Side.Sell, 1050, 10)
    assert r.trades == []
    assert r.final_status == OrderStatus.New
    assert engine.book.best_ask() == 1050


def test_limit_buy_below_best_ask_does_not_match(engine):
    engine.submit_limit(1, Side.Sell, 1050, 10)
    r = engine.submit_limit(2, Side.Buy, 1040, 10)
    assert r.trades == []
    assert r.final_status == OrderStatus.New


# ── Exact match ───────────────────────────────────────────────────────────────

def test_exact_fill_one_sell_one_buy(engine):
    engine.submit_limit(1, Side.Sell, 1000, 50)
    r = engine.submit_limit(2, Side.Buy, 1000, 50)
    assert len(r.trades) == 1
    assert r.trades[0].aggressor_id == 2
    assert r.trades[0].resting_id   == 1
    assert r.trades[0].price        == 1000
    assert r.trades[0].qty          == 50
    assert r.final_status == OrderStatus.Filled
    assert engine.book.is_empty()


def test_execution_at_maker_price(engine):
    engine.submit_limit(1, Side.Sell, 1000, 10)
    r = engine.submit_limit(2, Side.Buy, 1050, 10)
    assert len(r.trades) == 1
    assert r.trades[0].price == 1000   # maker price


# ── Partial fills ─────────────────────────────────────────────────────────────

def test_aggressor_partially_fills_and_rests(engine):
    engine.submit_limit(1, Side.Sell, 1000, 30)
    r = engine.submit_limit(2, Side.Buy, 1000, 50)
    assert r.trades[0].qty == 30
    assert r.final_status == OrderStatus.PartiallyFilled
    assert engine.book.bid_qty_at(1000) == 20


def test_resting_order_partially_filled(engine):
    engine.submit_limit(1, Side.Sell, 1000, 50)
    r = engine.submit_limit(2, Side.Buy, 1000, 20)
    assert r.trades[0].qty == 20
    assert r.final_status == OrderStatus.Filled
    assert engine.book.ask_qty_at(1000) == 30


# ── Multi-level sweep ─────────────────────────────────────────────────────────

def test_buy_sweeps_multiple_ask_levels(engine):
    engine.submit_limit(10, Side.Sell, 1000, 20)
    engine.submit_limit(11, Side.Sell, 1010, 20)
    engine.submit_limit(12, Side.Sell, 1020, 20)
    r = engine.submit_limit(20, Side.Buy, 1020, 55)
    assert len(r.trades) == 3
    assert r.trades[0].price == 1000
    assert r.trades[0].qty   == 20
    assert r.trades[1].price == 1010
    assert r.trades[1].qty   == 20
    assert r.trades[2].price == 1020
    assert r.trades[2].qty   == 15
    assert r.final_status == OrderStatus.Filled   # 20+20+15 = 55


# ── FIFO ──────────────────────────────────────────────────────────────────────

def test_fifo_within_price_level(engine):
    engine.submit_limit(1, Side.Sell, 1000, 10)
    engine.submit_limit(2, Side.Sell, 1000, 10)
    r = engine.submit_limit(3, Side.Buy, 1000, 15)
    assert r.trades[0].resting_id == 1   # first in, first out


# ── Market orders ─────────────────────────────────────────────────────────────

def test_market_order_full_fill(engine):
    engine.submit_limit(1, Side.Sell, 1000, 50)
    r = engine.submit_market(2, Side.Buy, 50)
    assert r.trades[0].qty == 50
    assert r.final_status == OrderStatus.Filled


def test_market_order_ioc_cancels_residual(engine):
    engine.submit_limit(1, Side.Sell, 1000, 20)
    r = engine.submit_market(2, Side.Buy, 50)
    assert r.trades[0].qty == 20
    assert r.cancel_event is not None
    assert r.cancel_event.remaining_qty == 30
    assert r.final_status == OrderStatus.PartiallyFilled


def test_market_order_on_empty_book_cancelled(engine):
    r = engine.submit_market(1, Side.Buy, 100)
    assert r.trades == []
    assert r.cancel_event is not None
    assert r.final_status == OrderStatus.Cancelled


# ── Cancel ────────────────────────────────────────────────────────────────────

def test_cancel_resting_order(engine):
    engine.submit_limit(1, Side.Buy, 1000, 100)
    r = engine.cancel_order(1)
    assert r.cancel_event is not None
    assert r.cancel_event.order_id == 1
    assert r.final_status == OrderStatus.Cancelled
    assert engine.book.best_bid() is None


def test_cancel_non_existent_order(engine):
    r = engine.cancel_order(999)
    assert r.reject_event is not None
    assert r.final_status == OrderStatus.Rejected


def test_cancel_then_match_does_not_use_removed_order(engine):
    engine.submit_limit(1, Side.Sell, 1000, 50)
    engine.cancel_order(1)
    r = engine.submit_limit(2, Side.Buy, 1000, 50)
    assert r.trades == []
    assert r.final_status == OrderStatus.New


# ── Invariants ────────────────────────────────────────────────────────────────

def test_no_crossed_book_after_match(engine):
    engine.submit_limit(1, Side.Sell, 1000, 20)
    engine.submit_limit(2, Side.Buy, 1000, 30)
    bb = engine.book.best_bid()
    ba = engine.book.best_ask()
    if bb is not None and ba is not None:
        assert bb < ba


def test_seq_counter_increases(engine):
    before = engine.seq_counter
    engine.submit_limit(1, Side.Buy, 1000, 10)
    assert engine.seq_counter > before
