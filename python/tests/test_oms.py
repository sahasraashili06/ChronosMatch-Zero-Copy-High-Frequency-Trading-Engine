"""Tests for OrderManagementSystem"""
import pytest
from chronosx.oms import OrderManagementSystem, OrderRequest
from chronosx.risk_engine import RiskEngine
from chronosx.types import Side, OrderType, OrderStatus, RiskResult


@pytest.fixture
def oms():
    return OrderManagementSystem(RiskEngine())


def _req(id, side=Side.Buy, type=OrderType.Limit, price=100_000, qty=10):
    return OrderRequest(id=id, side=side, type=type, price=price, qty=qty)


def test_submit_limit_new(oms):
    resp = oms.submit(_req(1))
    assert resp.match_result.final_status == OrderStatus.New
    assert resp.risk_result == RiskResult.Approved


def test_submit_rejected_by_risk(oms):
    resp = oms.submit(_req(1, qty=99_999))
    assert resp.match_result.final_status == OrderStatus.Rejected
    assert resp.risk_result == RiskResult.RejectedQty


def test_submit_and_match(oms):
    oms.submit(_req(1, side=Side.Sell, price=100_000, qty=10))
    resp = oms.submit(_req(2, side=Side.Buy, price=100_000, qty=10))
    assert resp.match_result.final_status == OrderStatus.Filled
    assert len(resp.match_result.trades) == 1


def test_cancel_existing_order(oms):
    oms.submit(_req(1))
    resp = oms.cancel(1)
    assert resp.match_result.final_status == OrderStatus.Cancelled


def test_cancel_nonexistent_order(oms):
    resp = oms.cancel(999)
    assert resp.match_result.final_status == OrderStatus.Rejected


def test_order_count_tracks_submissions(oms):
    oms.submit(_req(1))
    oms.submit(_req(2))
    assert oms.order_count == 2


def test_market_order_ioc(oms):
    oms.submit(_req(1, side=Side.Sell, price=100_000, qty=5))
    resp = oms.submit(OrderRequest(
        id=2, side=Side.Buy, type=OrderType.Market, price=0, qty=20
    ))
    assert resp.match_result.cancel_event is not None
    assert resp.match_result.cancel_event.remaining_qty == 15


def test_zero_qty_rejected(oms):
    resp = oms.submit(_req(1, qty=0))
    assert resp.match_result.final_status == OrderStatus.Rejected
