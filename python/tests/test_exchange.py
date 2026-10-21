"""Tests for Exchange (multi-instrument router)"""
import pytest
from chronosx.exchange import Exchange, InstrumentInfo
from chronosx.oms import OrderRequest
from chronosx.types import Side, OrderType, OrderStatus


@pytest.fixture
def ex():
    exchange = Exchange()
    exchange.list_instrument(InstrumentInfo("AAPL",  ref_price=182_000))
    exchange.list_instrument(InstrumentInfo("GOOGL", ref_price=140_000))
    return exchange


def _req(id, side=Side.Buy, price=100_000, qty=10):
    return OrderRequest(id=id, side=side, type=OrderType.Limit,
                        price=price, qty=qty)


def test_symbols_listed(ex):
    syms = ex.symbols()
    assert "AAPL"  in syms
    assert "GOOGL" in syms


def test_submit_to_correct_instrument(ex):
    resp = ex.submit("AAPL", _req(1, Side.Buy, price=180_000, qty=50))
    assert resp.match_result.final_status == OrderStatus.New
    # Book should be empty on GOOGL
    assert ex.session("GOOGL").best_bid() is None


def test_instruments_isolated(ex):
    ex.submit("AAPL",  _req(1, Side.Buy,  price=182_000, qty=10))
    ex.submit("GOOGL", _req(2, Side.Sell, price=140_000, qty=10))
    assert ex.session("AAPL").best_bid()  == 182_000
    assert ex.session("GOOGL").best_ask() == 140_000


def test_cross_within_instrument(ex):
    ex.submit("AAPL", _req(1, Side.Sell, price=182_000, qty=10))
    resp = ex.submit("AAPL", _req(2, Side.Buy, price=182_000, qty=10))
    assert resp.match_result.final_status == OrderStatus.Filled
    assert len(resp.match_result.trades)  == 1


def test_no_cross_across_instruments(ex):
    ex.submit("AAPL",  _req(1, Side.Sell, price=100_000, qty=10))
    resp = ex.submit("GOOGL", _req(2, Side.Buy, price=100_000, qty=10))
    # GOOGL should not see AAPL's resting order
    assert resp.match_result.trades == []


def test_cancel_on_correct_instrument(ex):
    ex.submit("AAPL", _req(1, Side.Buy, price=180_000, qty=10))
    r = ex.cancel("AAPL", 1)
    assert r.match_result.final_status == OrderStatus.Cancelled
    assert ex.session("AAPL").best_bid() is None


def test_unknown_instrument_raises(ex):
    with pytest.raises(KeyError):
        ex.submit("INVALID", _req(1))


def test_duplicate_listing_raises(ex):
    with pytest.raises(ValueError):
        ex.list_instrument(InstrumentInfo("AAPL"))


def test_total_trade_count(ex):
    ex.submit("AAPL",  _req(1, Side.Sell, price=182_000, qty=10))
    ex.submit("AAPL",  _req(2, Side.Buy,  price=182_000, qty=10))
    ex.submit("GOOGL", _req(3, Side.Sell, price=140_000, qty=5))
    ex.submit("GOOGL", _req(4, Side.Buy,  price=140_000, qty=5))
    assert ex.total_trade_count() == 2


def test_book_subscription(ex):
    snaps = []
    ex.subscribe_book("AAPL", snaps.append)
    ex.submit("AAPL", _req(1, Side.Buy, price=181_000, qty=20))
    assert len(snaps) == 1
    assert snaps[0].instrument_id == "AAPL"
