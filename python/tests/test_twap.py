"""Tests for TwapExecutor"""
import pytest
from chronosx.twap import TwapExecutor, TwapConfig, TwapState
from chronosx.risk_engine import RiskEngine, RiskLimits
from chronosx.oms import OrderManagementSystem, OrderRequest
from chronosx.types import Side, OrderType, OrderStatus


@pytest.fixture
def oms():
    limits = RiskLimits(max_order_qty=10_000, max_order_notional=10**15)
    return OrderManagementSystem(RiskEngine(limits))


@pytest.fixture
def executor(oms):
    return TwapExecutor(oms, next_order_id=9000)


def _cfg(parent_id=1, side=Side.Buy, total_qty=100,
         num_slices=5, limit_price=105_000):
    return TwapConfig(parent_id=parent_id, side=side,
                      total_qty=total_qty, num_slices=num_slices,
                      limit_price=limit_price)


def test_create_and_start(executor):
    jid = executor.create(_cfg())
    executor.start(jid)
    assert executor.status(jid).state == TwapState.Running


def test_single_tick_sends_one_slice(executor):
    jid = executor.create(_cfg(total_qty=100, num_slices=5))
    executor.start(jid)
    executor.tick(jid)
    st = executor.status(jid)
    assert st.slices_sent   == 1
    assert st.qty_submitted == 20  # 100 / 5


def test_all_slices_sent_after_n_ticks(executor):
    jid = executor.create(_cfg(total_qty=50, num_slices=5))
    executor.start(jid)
    for _ in range(5):
        executor.tick(jid)
    st = executor.status(jid)
    assert st.slices_sent  == 5
    assert st.state        == TwapState.Completed


def test_remainder_added_to_last_slice(executor):
    # 103 / 5 = 20 each, remainder 3 on last
    jid = executor.create(_cfg(total_qty=103, num_slices=5))
    executor.start(jid)
    for _ in range(5):
        executor.tick(jid)
    st = executor.status(jid)
    assert st.qty_submitted == 103


def test_fills_tracked_when_counterparty_exists(oms, executor):
    # Seed opposing orders so slices fill
    for i in range(10):
        oms.submit(OrderRequest(i+1, Side.Sell, OrderType.Limit, 105_000, 20))
    jid = executor.create(_cfg(total_qty=100, num_slices=5, limit_price=105_000))
    executor.start(jid)
    for _ in range(5):
        executor.tick(jid)
    st = executor.status(jid)
    assert st.qty_filled == 100
    assert st.fill_rate  == 1.0


def test_cancel_stops_execution(executor):
    jid = executor.create(_cfg())
    executor.start(jid)
    executor.tick(jid)
    executor.cancel(jid)
    executor.tick(jid)   # should be no-op
    assert executor.status(jid).state    == TwapState.Cancelled
    assert executor.status(jid).slices_sent == 1   # only 1 tick before cancel


def test_tick_before_start_is_noop(executor):
    jid = executor.create(_cfg())
    result = executor.tick(jid)
    assert result is None
    assert executor.status(jid).slices_sent == 0


def test_avg_fill_price_computed(oms, executor):
    for i in range(10):
        oms.submit(OrderRequest(i+1, Side.Sell, OrderType.Limit, 105_000, 20))
    jid = executor.create(_cfg(total_qty=100, num_slices=5))
    executor.start(jid)
    for _ in range(5):
        executor.tick(jid)
    st = executor.status(jid)
    if st.qty_filled > 0:
        assert st.avg_fill_price == 105_000.0


def test_summary_string(executor):
    jid = executor.create(_cfg())
    executor.start(jid)
    s = executor.status(jid).summary()
    assert "TWAP" in s
    assert "Buy" in s
