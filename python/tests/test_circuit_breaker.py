"""Tests for CircuitBreaker"""
import time
import pytest
from chronosx.circuit_breaker import CircuitBreaker, BreakerConfig, BreakerState


@pytest.fixture
def cb():
    return CircuitBreaker(BreakerConfig(
        max_price_move_pct=2.0,
        window_sec=60.0,
        max_loss_fixed=100_000,   # $10.00
        max_reject_rate=0.5,
        reject_window=4,
        cooldown_sec=30.0,
    ))


def test_initial_state_closed(cb):
    assert cb.state    == BreakerState.CLOSED
    assert cb.is_closed is True
    assert cb.allow()  is True


def test_no_trip_on_small_price_move(cb):
    cb.on_price(100_000)
    cb.on_price(100_500)   # 0.5% move — under 2% threshold
    assert cb.is_closed


def test_trip_on_large_price_move(cb):
    cb.on_price(100_000)
    tripped = cb.on_price(103_000)   # 3% move
    assert tripped is True
    assert cb.is_open
    assert cb.allow() is False


def test_pnl_trip(cb):
    tripped = cb.on_pnl_update(realised=-80_000, unrealised=-30_000)
    assert tripped is True
    assert cb.is_open


def test_pnl_no_trip_within_limit(cb):
    tripped = cb.on_pnl_update(realised=-50_000, unrealised=-40_000)
    assert tripped is False
    assert cb.is_closed


def test_rejection_rate_trip(cb):
    # 3 rejections out of 4 = 75% > 50%
    cb.on_order_result(False)
    cb.on_order_result(False)
    cb.on_order_result(False)
    tripped = cb.on_order_result(True)
    assert tripped is True
    assert cb.is_open


def test_rejection_rate_no_trip(cb):
    cb.on_order_result(True)
    cb.on_order_result(True)
    cb.on_order_result(False)
    tripped = cb.on_order_result(True)   # 25% reject rate
    assert tripped is False
    assert cb.is_closed


def test_manual_reset(cb):
    cb.on_price(100_000)
    cb.on_price(103_000)
    assert cb.is_open
    cb.reset()
    assert cb.is_closed
    assert cb.allow() is True


def test_events_recorded(cb):
    cb.on_price(100_000)
    cb.on_price(103_000)
    cb.on_pnl_update(realised=0, unrealised=0)   # won't double-trip (already open)
    assert len(cb.events) == 1
    assert "Volatility" in cb.events[0].reason


def test_trip_count(cb):
    cb.on_price(100_000)
    cb.on_price(103_000)
    assert cb.trip_count == 1


def test_allow_blocks_when_open(cb):
    cb.on_pnl_update(realised=-200_000, unrealised=0)
    assert cb.allow() is False
    assert cb.allow() is False   # still blocked
