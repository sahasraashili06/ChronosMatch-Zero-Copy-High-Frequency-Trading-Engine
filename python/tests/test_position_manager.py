"""Tests for PositionManager"""
import pytest
from chronosx.position_manager import PositionManager, Fill
from chronosx.types import Side, TradeEvent


@pytest.fixture
def pm():
    return PositionManager()


def _trade(agg_id, rest_id, price, qty):
    return TradeEvent(aggressor_id=agg_id, resting_id=rest_id, price=price, qty=qty)


def test_empty_position_returns_none(pm):
    assert pm.get_position(99) is None


def test_trade_creates_positions(pm):
    pm.record_trade(_trade(1, 2, 1000, 10), Side.Buy)
    assert pm.get_position(1) is not None   # aggressor
    assert pm.get_position(2) is not None   # resting


def test_aggressor_buy_is_long(pm):
    pm.record_trade(_trade(1, 2, 1000, 10), Side.Buy)
    pos = pm.get_position(1)
    assert pos.net_qty == 10   # bought


def test_resting_sell_is_short(pm):
    pm.record_trade(_trade(1, 2, 1000, 10), Side.Buy)
    pos = pm.get_position(2)
    assert pos.net_qty == -10   # was resting sell


def test_avg_entry_price_correct(pm):
    pm.record_trade(_trade(1, 2, 1000, 10), Side.Buy)
    pos = pm.get_position(1)
    assert pos.avg_entry == 1000.0


def test_adding_to_position_updates_vwap(pm):
    pm.record_trade(_trade(1, 2, 1000, 10), Side.Buy)
    pm.record_trade(_trade(1, 3, 1100, 10), Side.Buy)
    pos = pm.get_position(1)
    assert pos.net_qty   == 20
    assert pos.avg_entry == 1050.0   # (1000*10 + 1100*10) / 20


def test_closing_position_realises_pnl(pm):
    pm.record_trade(_trade(1, 2, 1000, 10), Side.Buy)    # participant 1 buys 10 @ 1000
    # participant 1 is now aggressor selling — same id closes the position
    pm.record_trade(_trade(1, 3, 1200, 10), Side.Sell)   # sell 10 @ 1200 (participant 1 as aggressor)
    pos = pm.get_position(1)
    assert pos.net_qty == 0
    assert pos.realised_pnl == 2000   # 10 * (1200-1000)


def test_total_volume_accumulates(pm):
    pm.record_trade(_trade(1, 2, 1000, 5),  Side.Buy)
    pm.record_trade(_trade(3, 4, 1000, 15), Side.Sell)
    assert pm.total_volume == 20


def test_vwap(pm):
    pm.record_trade(_trade(1, 2, 1000, 10), Side.Buy)
    pm.record_trade(_trade(3, 4, 1100, 10), Side.Sell)
    # (1000*10 + 1100*10) / 20 = 1050
    assert pm.vwap() == 1050.0


def test_position_is_flat_after_full_close(pm):
    pm.record_trade(_trade(1, 2, 1000, 10), Side.Buy)    # participant 1 buys 10
    pm.record_trade(_trade(1, 3, 1000, 10), Side.Sell)   # participant 1 sells 10 (closes)
    pos = pm.get_position(1)
    assert pos.is_flat()


def test_unrealised_pnl(pm):
    pm.record_trade(_trade(1, 2, 1000, 10), Side.Buy)
    pos = pm.get_position(1)
    # mark at 1050: unrealised = 10 * (1050-1000) = 500
    assert pos.unrealised_pnl(1050) == 500.0
