"""Tests for BacktestEngine and BacktestResult."""
import io
import pytest
from chronosx.backtester import BacktestEngine, BacktestResult, Strategy, PassiveStrategy
from chronosx.replay import parse_csv, ReplayEvent
from chronosx.types import Side, OrderType, TradeEvent
from chronosx.oms import OrderRequest
from chronosx.order_book import OrderBook
from chronosx.position_manager import Position
from typing import List, Optional


# ── Minimal test strategy ─────────────────────────────────────────────────────

class DoNothingStrategy(Strategy):
    def on_event(self, event, book, position):
        return []


class AlwaysBuyStrategy(Strategy):
    """Sends one market buy on every event."""
    def __init__(self):
        self._id = 50_000

    def on_event(self, event, book, position):
        req = OrderRequest(self._id, Side.Buy, OrderType.Market, 0, 5)
        self._id += 1
        return [req]


CSV = """\
ts_ns,order_id,side,type,price,qty
1000,1,Sell,Limit,100000,100
2000,2,Sell,Limit,100000,100
3000,3,Sell,Limit,100000,100
"""


@pytest.fixture
def events():
    return parse_csv(io.StringIO(CSV))


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_do_nothing_no_trades(events):
    result = BacktestEngine(DoNothingStrategy()).run(events)
    assert result.trade_count   == 0
    assert result.orders_sent   == 0
    assert result.total_pnl_usd == 0.0


def test_returns_backtest_result(events):
    result = BacktestEngine(DoNothingStrategy()).run(events)
    assert isinstance(result, BacktestResult)


def test_total_events_counted(events):
    result = BacktestEngine(DoNothingStrategy()).run(events)
    assert result.total_events == 3


def test_always_buy_sends_orders(events):
    result = BacktestEngine(AlwaysBuyStrategy()).run(events)
    assert result.orders_sent == 3


def test_always_buy_fills(events):
    result = BacktestEngine(AlwaysBuyStrategy()).run(events)
    assert result.orders_filled >= 1
    assert result.trade_count   >= 1


def test_fill_rate_in_range(events):
    result = BacktestEngine(AlwaysBuyStrategy()).run(events)
    assert 0.0 <= result.fill_rate <= 1.0


def test_strategy_name_is_class_name(events):
    result = BacktestEngine(DoNothingStrategy()).run(events)
    assert result.strategy_name == "DoNothingStrategy"


def test_sharpe_zero_with_no_trades(events):
    result = BacktestEngine(DoNothingStrategy()).run(events)
    assert result.sharpe == 0.0


def test_max_drawdown_non_negative(events):
    result = BacktestEngine(AlwaysBuyStrategy()).run(events)
    assert result.max_drawdown >= 0.0


def test_win_rate_in_range(events):
    result = BacktestEngine(AlwaysBuyStrategy()).run(events)
    assert 0.0 <= result.win_rate <= 1.0


def test_summary_string_contains_key_fields(events):
    result = BacktestEngine(DoNothingStrategy()).run(events)
    s = result.summary()
    assert "Sharpe"   in s
    assert "P&L"      in s
    assert "Win rate" in s


def test_empty_events():
    result = BacktestEngine(DoNothingStrategy()).run([])
    assert result.total_events == 0
    assert result.trade_count  == 0


def test_pnl_series_grows_with_trades(events):
    result = BacktestEngine(AlwaysBuyStrategy()).run(events)
    # pnl_series has one entry per fill
    assert len(result.pnl_series) == result.trade_count
