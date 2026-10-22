"""Tests for MarketDataPublisher"""
import pytest
from chronosx.market_data import MarketDataPublisher, BookSnapshot, TradeReport
from chronosx.matching_engine import MatchingEngine
from chronosx.types import Side, TradeEvent


@pytest.fixture
def engine():
    return MatchingEngine()


@pytest.fixture
def pub():
    return MarketDataPublisher("TEST", depth=5)


def test_book_subscriber_called_on_event(engine, pub):
    received = []
    pub.subscribe_book(received.append)

    engine.submit_limit(1, Side.Sell, 1000, 50)
    pub.on_order_event(engine.book, [], Side.Sell)

    assert len(received) == 1
    assert isinstance(received[0], BookSnapshot)


def test_snapshot_has_correct_ask(engine, pub):
    received = []
    pub.subscribe_book(received.append)

    engine.submit_limit(1, Side.Sell, 1050, 30)
    pub.on_order_event(engine.book, [], Side.Sell)

    snap = received[0]
    assert len(snap.asks) == 1
    assert snap.asks[0].price == 1050
    assert snap.asks[0].qty   == 30


def test_snapshot_bid_ask_depth(engine, pub):
    received = []
    pub.subscribe_book(received.append)

    for i, p in enumerate([1010, 1020, 1030], 1):
        engine.submit_limit(i, Side.Sell, p, 10)
    for i, p in enumerate([990, 980, 970], 10):
        engine.submit_limit(i, Side.Buy, p, 10)

    pub.on_order_event(engine.book, [], Side.Buy)
    snap = received[0]

    assert len(snap.asks) == 3
    assert len(snap.bids) == 3
    assert snap.best_ask.price == 1010   # type: ignore
    assert snap.best_bid.price == 990    # type: ignore


def test_spread_computation(engine, pub):
    received = []
    pub.subscribe_book(received.append)

    engine.submit_limit(1, Side.Sell, 1010, 10)
    engine.submit_limit(2, Side.Buy,   990, 10)
    pub.on_order_event(engine.book, [], Side.Buy)

    snap = received[0]
    assert snap.spread == 20


def test_trade_subscriber_receives_reports(engine, pub):
    trades_received = []
    pub.subscribe_trades(trades_received.append)

    engine.submit_limit(1, Side.Sell, 1000, 20)
    r = engine.submit_limit(2, Side.Buy, 1000, 20)
    pub.on_order_event(engine.book, r.trades, Side.Buy)

    assert len(trades_received) == 1
    tr = trades_received[0]
    assert tr.price == 1000
    assert tr.qty   == 20
    assert tr.aggressor_side == Side.Buy


def test_no_trade_subscriber_when_no_trades(engine, pub):
    received = []
    pub.subscribe_trades(received.append)

    engine.submit_limit(1, Side.Buy, 900, 10)
    pub.on_order_event(engine.book, [], Side.Buy)

    assert received == []


def test_seq_monotonically_increases(engine, pub):
    snaps = []
    pub.subscribe_book(snaps.append)

    for i in range(1, 4):
        engine.submit_limit(i, Side.Buy, 1000 - i, 10)
        pub.on_order_event(engine.book, [], Side.Buy)

    seqs = [s.seq for s in snaps]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 3   # all unique


def test_instrument_id_propagated(engine, pub):
    received = []
    pub.subscribe_book(received.append)
    engine.submit_limit(1, Side.Sell, 1000, 10)
    pub.on_order_event(engine.book, [], Side.Sell)
    assert received[0].instrument_id == "TEST"
