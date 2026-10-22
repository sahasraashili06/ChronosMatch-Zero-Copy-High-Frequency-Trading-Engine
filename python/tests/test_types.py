"""Tests for types.py"""
import pytest
from chronosx.types import (
    PRICE_MULT, INVALID_ORDER_ID, INVALID_PRICE,
    Side, OrderType, OrderStatus, RiskResult,
    TradeEvent, CancelEvent, RejectEvent, MatchResult,
)


def test_price_mult():
    assert PRICE_MULT == 10_000


def test_invalid_sentinels():
    assert INVALID_ORDER_ID == 0
    assert INVALID_PRICE < 0


def test_side_values():
    assert Side.Buy  == 0
    assert Side.Sell == 1


def test_order_type_values():
    assert OrderType.Limit  == 0
    assert OrderType.Market == 1


def test_order_status_values():
    assert OrderStatus.New             == 0
    assert OrderStatus.PartiallyFilled == 1
    assert OrderStatus.Filled          == 2
    assert OrderStatus.Cancelled       == 3
    assert OrderStatus.Rejected        == 4


def test_trade_event_default():
    t = TradeEvent()
    assert t.aggressor_id == INVALID_ORDER_ID
    assert t.resting_id   == INVALID_ORDER_ID
    assert t.price        == INVALID_PRICE
    assert t.qty          == 0


def test_match_result_default():
    mr = MatchResult()
    assert mr.trades       == []
    assert mr.cancel_event is None
    assert mr.reject_event is None
    assert mr.final_status == OrderStatus.New
