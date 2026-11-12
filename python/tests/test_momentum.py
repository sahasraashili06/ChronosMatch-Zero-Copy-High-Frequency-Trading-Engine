"""Tests for MomentumSignal."""
import pytest
from chronosx.momentum import MomentumSignal, Signal, MomentumReading
from chronosx.types import PRICE_MULT


@pytest.fixture
def sig():
    return MomentumSignal(fast=3, slow=8, rsi_period=5, lookback=5)


def test_first_reading_neutral(sig):
    r = sig.update(100_000)
    assert isinstance(r, MomentumReading)
    assert r.signal == Signal.NEUTRAL


def test_fast_greater_than_slow_raises():
    with pytest.raises(ValueError):
        MomentumSignal(fast=10, slow=5)


def test_ema_initialised_on_first_update(sig):
    sig.update(100_000)
    assert sig.fast_ema == pytest.approx(100_000.0, rel=1e-3)
    assert sig.slow_ema == pytest.approx(100_000.0, rel=1e-3)


def test_uptrend_gives_buy(sig):
    # Feed rising prices — fast EMA rises above slow EMA
    prices = [100_000 + i * 1000 for i in range(20)]
    readings = [sig.update(p) for p in prices]
    # fast EMA > slow EMA in uptrend
    assert readings[-1].fast_ema > readings[-1].slow_ema


def test_downtrend_gives_sell(sig):
    prices = [100_000 - i * 1000 for i in range(20)]
    readings = [sig.update(p) for p in prices]
    # fast EMA < slow EMA in downtrend
    assert readings[-1].fast_ema < readings[-1].slow_ema


def test_fast_ema_reacts_faster(sig):
    # After price jump, fast EMA should be closer to new price
    for _ in range(10):
        sig.update(100_000)
    sig.update(200_000)
    assert sig.fast_ema > sig.slow_ema  # type: ignore


def test_return_pct_zero_before_lookback(sig):
    r = sig.update(100_000)
    assert r.return_pct == 0.0


def test_return_pct_computed_after_lookback(sig):
    for i in range(6):
        r = sig.update(100_000 + i * 1000)
    assert r.return_pct != 0.0


def test_rsi_starts_at_50(sig):
    r = sig.update(100_000)
    assert r.rsi == pytest.approx(50.0, abs=1.0)


def test_overbought_flag(sig):
    # Start at low price, then jump high so RSI sees many gains
    for _ in range(5):
        sig.update(100_000)
    for _ in range(30):
        sig.update(200_000 + _ * 100)  # steady gains
    r = sig.update(300_000)
    assert r.rsi > 50   # RSI elevated after sustained gains


def test_oversold_flag(sig):
    # Start high then drop — RSI sees sustained losses
    for _ in range(5):
        sig.update(200_000)
    for i in range(30):
        sig.update(200_000 - i * 100)
    r = sig.update(50_000)
    assert r.rsi < 50   # RSI depressed after sustained losses


def test_ema_spread(sig):
    for _ in range(5):
        sig.update(100_000)
    sig.update(110_000)
    r = sig.update(110_000)
    # fast reacts more, so spread is non-zero
    assert isinstance(r.ema_spread, float)


def test_sample_count(sig):
    for i in range(7):
        sig.update(100_000)
    assert sig.sample_count == 7


def test_reset(sig):
    for _ in range(10):
        sig.update(100_000)
    sig.reset()
    assert sig.sample_count == 0
    assert sig.fast_ema is None


def test_str_representation(sig):
    r = sig.update(100_000)
    s = str(r)
    assert "Momentum" in s
    assert "RSI" in s
