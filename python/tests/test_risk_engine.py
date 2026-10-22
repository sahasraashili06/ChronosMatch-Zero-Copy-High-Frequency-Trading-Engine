"""Tests for RiskEngine"""
import pytest
from chronosx.risk_engine import RiskEngine, RiskLimits
from chronosx.types import Side, RiskResult


@pytest.fixture
def engine():
    return RiskEngine()


def test_approved_normal_order(engine):
    assert engine.check_order(Side.Buy, 100_000, 10) == RiskResult.Approved


def test_rejected_qty_too_large(engine):
    assert engine.check_order(Side.Buy, 1_000, 99_999) == RiskResult.RejectedQty


def test_rejected_notional_too_large(engine):
    # limit = 10_000_000 * 10_000 = 100_000_000_000
    # 9_999 * 15_000_000 = 149_985_000_000  > limit  → RejectedNotional
    assert engine.check_order(Side.Buy, 15_000_000, 9_999) == RiskResult.RejectedNotional


def test_boundary_qty_exactly_at_limit(engine):
    assert engine.check_order(Side.Buy, 1, 10_000) == RiskResult.Approved


def test_boundary_qty_one_over_limit(engine):
    assert engine.check_order(Side.Buy, 1, 10_001) == RiskResult.RejectedQty


def test_zero_price_not_checked_for_notional(engine):
    # Market orders pass price=0; should not reject on notional
    assert engine.check_order(Side.Buy, 0, 10_000) == RiskResult.Approved


def test_custom_limits():
    limits = RiskLimits(max_order_qty=5, max_order_notional=50_000)
    engine = RiskEngine(limits)
    assert engine.check_order(Side.Buy, 1_000, 5)  == RiskResult.Approved
    assert engine.check_order(Side.Buy, 1_000, 6)  == RiskResult.RejectedQty
    assert engine.check_order(Side.Buy, 10_000, 6) == RiskResult.RejectedQty


def test_sell_side_also_checked(engine):
    assert engine.check_order(Side.Sell, 100_000, 10) == RiskResult.Approved
    assert engine.check_order(Side.Sell, 100_000, 99_999) == RiskResult.RejectedQty
