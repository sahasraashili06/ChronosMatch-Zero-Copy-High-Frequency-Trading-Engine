"""Tests for VpinEstimator (order flow toxicity)."""
import pytest
from chronosx.vpin import VpinEstimator, VpinBucket
from chronosx.types import Side, TradeEvent


def _trade(qty: int) -> TradeEvent:
    return TradeEvent(aggressor_id=1, resting_id=2, price=100_000, qty=qty)


@pytest.fixture
def vpin():
    return VpinEstimator(bucket_size=100, window=5)


def test_initial_vpin_zero(vpin):
    assert vpin.current     == 0.0
    assert vpin.bucket_count == 0


def test_incomplete_bucket_no_vpin(vpin):
    vpin.on_trade(_trade(50), Side.Buy)
    assert vpin.bucket_count == 0
    assert vpin.current      == 0.0


def test_one_full_bucket_all_buy(vpin):
    vpin.on_trade(_trade(100), Side.Buy)
    assert vpin.bucket_count == 1
    assert vpin.current      == pytest.approx(1.0)


def test_one_full_bucket_balanced(vpin):
    vpin.on_trade(_trade(50), Side.Buy)
    vpin.on_trade(_trade(50), Side.Sell)
    assert vpin.bucket_count == 1
    assert vpin.current      == pytest.approx(0.0)


def test_one_full_bucket_mixed(vpin):
    vpin.on_trade(_trade(70), Side.Buy)
    vpin.on_trade(_trade(30), Side.Sell)
    assert vpin.bucket_count == 1
    assert vpin.current      == pytest.approx(0.4)


def test_large_trade_spans_multiple_buckets(vpin):
    vpin.on_trade(_trade(300), Side.Buy)   # fills 3 buckets
    assert vpin.bucket_count == 3
    assert vpin.current      == pytest.approx(1.0)


def test_rolling_window_caps_at_window(vpin):
    for _ in range(10):   # send 10 buckets, window=5
        vpin.on_trade(_trade(100), Side.Buy)
    assert vpin.bucket_count == 5   # capped at window


def test_toxicity_label_high(vpin):
    vpin.on_trade(_trade(100), Side.Buy)   # all buys → VPIN=1.0
    assert vpin.toxicity_label == "HIGH"


def test_toxicity_label_low(vpin):
    vpin.on_trade(_trade(50), Side.Buy)
    vpin.on_trade(_trade(50), Side.Sell)   # balanced → VPIN=0.0
    assert vpin.toxicity_label == "LOW"


def test_pending_volume_tracked(vpin):
    vpin.on_trade(_trade(40), Side.Buy)
    assert vpin.pending_volume() == 40


def test_on_volume_convenience(vpin):
    vpin.on_volume(100, Side.Sell)
    assert vpin.bucket_count == 1
    assert vpin.current      == pytest.approx(1.0)


def test_invalid_bucket_size_raises():
    with pytest.raises(ValueError):
        VpinEstimator(bucket_size=0)


def test_invalid_window_raises():
    with pytest.raises(ValueError):
        VpinEstimator(bucket_size=100, window=0)


def test_str_representation(vpin):
    vpin.on_trade(_trade(100), Side.Buy)
    s = str(vpin)
    assert "VPIN" in s
    assert "HIGH" in s
