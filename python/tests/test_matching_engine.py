
"""Tests for MatchingEngine — matching, execution, and cancellation scenarios."""

import pytest
from chronosx.matching_engine import MatchingEngine
from chronosx.types import Side, OrderStatus


@pytest.fixture
def engine():
    return MatchingEngine()


def test_limit_buy_rests_when_no_ask(engine):
    result = engine.submit_limit(1, Side.Buy, 1000, 10)
    assert result.final_status == OrderStatus.New
    assert engine.book.best_bid() == 1000


def test_limit_sell_rests_when_no_bid(engine):
    result = engine.submit_limit(1, Side.Sell, 1010, 10)
    assert result.final_status == OrderStatus.New
    assert engine.book.best_ask() == 1010


def test_limit_buy_below_best_ask_does_not_match(engine):
    engine.submit_limit(1, Side.Sell, 1010, 10)
    result = engine.submit_limit(2, Side.Buy, 1000, 10)
    assert len(result.trades) == 0
    assert result.final_status == OrderStatus.New


def test_exact_fill_one_sell_one_buy(engine):
    engine.submit_limit(1, Side.Sell, 1000, 10)
    result = engine.submit_limit(2, Side.Buy, 1000, 10)
    assert len(result.trades) == 1
    assert result.trades[0].qty == 10
    assert result.final_status == OrderStatus.Filled


def test_execution_at_maker_price(engine):
    engine.submit_limit(1, Side.Sell, 1000, 10)
    result = engine.submit_limit(2, Side.Buy, 1010, 10)
    assert len(result.trades) == 1
    assert result.trades[0].price == 1000


def test_aggressor_partially_fills_and_rests(engine):
    engine.submit_limit(1, Side.Sell, 1000, 5)
    result = engine.submit_limit(2, Side.Buy, 1000, 10)

    assert len(result.trades) == 1
    assert result.trades[0].qty == 5
    assert result.final_status == OrderStatus.PartiallyFilled
    assert engine.book.bid_qty_at(1000) == 5


def test_resting_order_partially_filled(engine):
    engine.submit_limit(1, Side.Sell, 1000, 10)
    engine.submit_limit(2, Side.Buy, 1000, 4)
    assert engine.book.ask_qty_at(1000) == 6


def test_buy_sweeps_multiple_ask_levels(engine):
    engine.submit_limit(1, Side.Sell, 1000, 5)
    engine.submit_limit(2, Side.Sell, 1010, 5)
    result = engine.submit_limit(3, Side.Buy, 1010, 10)
    assert len(result.trades) == 2
    assert result.trades[0].price == 1000
    assert result.trades[1].price == 1010


def test_fifo_within_price_level(engine):
    engine.submit_limit(1, Side.Sell, 1000, 5)
    engine.submit_limit(2, Side.Sell, 1000, 5)
    result = engine.submit_limit(3, Side.Buy, 1000, 7)

    assert len(result.trades) == 2
    assert result.trades[0].resting_id == 1
    assert result.trades[0].qty == 5
    assert result.trades[1].resting_id == 2
    assert result.trades[1].qty == 2


def test_market_order_full_fill(engine):
    engine.submit_limit(1, Side.Sell, 1000, 10)
    result = engine.submit_market(2, Side.Buy, 10)
    assert len(result.trades) == 1
    assert result.final_status == OrderStatus.Filled


def test_market_order_ioc_cancels_residual(engine):
    engine.submit_limit(1, Side.Sell, 1000, 5)
    result = engine.submit_market(2, Side.Buy, 10)

    assert len(result.trades) == 1
    assert result.trades[0].qty == 5
    assert result.cancel_event is not None
    assert result.cancel_event.order_id == 2
    assert result.cancel_event.remaining_qty == 5
    assert result.final_status == OrderStatus.PartiallyFilled


def test_market_order_on_empty_book_cancelled(engine):
    result = engine.submit_market(1, Side.Buy, 10)
    assert len(result.trades) == 0
    assert result.final_status == OrderStatus.Cancelled


def test_cancel_resting_order(engine):
    engine.submit_limit(1, Side.Buy, 1000, 10)
    result = engine.cancel_order(1)
    assert result.final_status == OrderStatus.Cancelled


def test_cancel_non_existent_order(engine):
    result = engine.cancel_order(999)
    assert result.final_status == OrderStatus.Rejected


def test_cancel_then_match_does_not_use_removed_order(engine):
    engine.submit_limit(1, Side.Sell, 1000, 10)
    engine.cancel_order(1)
    result = engine.submit_limit(2, Side.Buy, 1000, 10)
    assert len(result.trades) == 0


def test_no_crossed_book_after_match(engine):
    engine.submit_limit(1, Side.Sell, 1000, 10)
    engine.submit_limit(2, Side.Buy, 1000, 10)

    best_bid = engine.book.best_bid()
    best_ask = engine.book.best_ask()

    if best_bid is not None and best_ask is not None:
        assert best_bid < best_ask


def test_seq_counter_increases(engine):
    engine.submit_limit(1, Side.Buy, 1000, 10)
    first_seq = engine.seq_counter
    engine.submit_limit(2, Side.Sell, 1010, 10)
    assert engine.seq_counter > first_seq


def test_sell_sweeps_multiple_bid_levels(engine):
    """A sell order should match the highest bids first."""
    engine.submit_limit(1, Side.Buy, 1020, 10)
    engine.submit_limit(2, Side.Buy, 1010, 10)
    engine.submit_limit(3, Side.Buy, 1000, 20)

    result = engine.submit_limit(4, Side.Sell, 1000, 25)

    assert len(result.trades) == 3

    assert result.trades[0].resting_id == 1
    assert result.trades[0].price == 1020
    assert result.trades[0].qty == 10

    assert result.trades[1].resting_id == 2
    assert result.trades[1].price == 1010
    assert result.trades[1].qty == 10

    assert result.trades[2].resting_id == 3
    assert result.trades[2].price == 1000
    assert result.trades[2].qty == 5

    assert result.final_status == OrderStatus.Filled
    assert engine.book.bid_qty_at(1000) == 15


def test_cancel_best_bid_exposes_next_price_level(engine):
    """Cancelling the best bid should expose the next-highest bid."""
    engine.submit_limit(1, Side.Buy, 1000, 10)
    engine.submit_limit(2, Side.Buy, 990, 20)

    assert engine.book.best_bid() == 1000

    result = engine.cancel_order(1)

    assert result.final_status == OrderStatus.Cancelled
    assert engine.book.best_bid() == 990
    assert engine.book.bid_qty_at(990) == 20
