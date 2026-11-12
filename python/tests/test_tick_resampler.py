"""Tests for TickResampler."""
import pytest
from chronosx.tick_resampler import TickResampler, ResampledBar


@pytest.fixture
def rs():
    return TickResampler(interval_sec=1.0)


# ---- Basic ------------------------------------------------------------------

def test_tick_within_interval_no_bar(rs):
    assert rs.on_tick(100_000, qty=10, timestamp=0.0) is None
    assert rs.on_tick(101_000, qty=10, timestamp=0.5) is None


def test_tick_crossing_interval_closes_bar(rs):
    rs.on_tick(100_000, qty=10, timestamp=0.0)
    bar = rs.on_tick(102_000, qty=10, timestamp=1.0)
    assert bar is not None
    assert isinstance(bar, ResampledBar)


def test_bar_count_after_crossing(rs):
    rs.on_tick(100_000, qty=1, timestamp=0.0)
    rs.on_tick(101_000, qty=1, timestamp=1.0)
    rs.on_tick(102_000, qty=1, timestamp=2.0)
    assert rs.bar_count == 2


# ---- OHLC correctness -------------------------------------------------------

def test_ohlc_values(rs):
    rs.on_tick(100_000, qty=1, timestamp=0.0)
    rs.on_tick(105_000, qty=1, timestamp=0.3)
    rs.on_tick(98_000,  qty=1, timestamp=0.7)
    bar = rs.on_tick(102_000, qty=1, timestamp=1.0)
    assert bar.open  == 100_000
    assert bar.high  == 105_000
    assert bar.low   == 98_000
    assert bar.close == 98_000


def test_volume_accumulated(rs):
    rs.on_tick(100_000, qty=30, timestamp=0.0)
    rs.on_tick(100_000, qty=20, timestamp=0.5)
    bar = rs.on_tick(100_000, qty=10, timestamp=1.0)
    assert bar.volume == 50


def test_tick_count(rs):
    for i in range(5):
        rs.on_tick(100_000, qty=1, timestamp=i * 0.1)
    bar = rs.on_tick(100_000, qty=1, timestamp=1.0)
    assert bar.tick_count == 5


# ---- VWAP -------------------------------------------------------------------

def test_vwap_uniform_price(rs):
    rs.on_tick(100_000, qty=50, timestamp=0.0)
    rs.on_tick(100_000, qty=50, timestamp=0.5)
    bar = rs.on_tick(100_000, qty=1, timestamp=1.0)
    from chronosx.types import PRICE_MULT
    assert bar.vwap == pytest.approx(100_000 / PRICE_MULT, abs=0.001)


# ---- Flush ------------------------------------------------------------------

def test_flush_partial_bar(rs):
    rs.on_tick(100_000, qty=10, timestamp=0.0)
    rs.on_tick(101_000, qty=10, timestamp=0.5)
    bar = rs.flush()
    assert bar is not None
    assert bar.tick_count == 2


def test_flush_empty_returns_none(rs):
    assert rs.flush() is None


def test_flush_after_flush_returns_none(rs):
    rs.on_tick(100_000, qty=1, timestamp=0.0)
    rs.flush()
    assert rs.flush() is None


# ---- Current snapshot -------------------------------------------------------

def test_current_snapshot(rs):
    rs.on_tick(100_000, qty=10, timestamp=0.0)
    snap = rs.current
    assert snap is not None
    assert snap["open"] == 100_000
    assert snap["volume"] == 10


def test_current_none_before_first_tick(rs):
    assert rs.current is None


# ---- Reset ------------------------------------------------------------------

def test_reset_clears_bars(rs):
    rs.on_tick(100_000, qty=1, timestamp=0.0)
    rs.on_tick(100_000, qty=1, timestamp=1.0)
    rs.reset()
    assert rs.bar_count == 0
    assert rs.current is None


# ---- Validation -------------------------------------------------------------

def test_invalid_interval_raises():
    with pytest.raises(ValueError):
        TickResampler(interval_sec=0)


def test_str_bar(rs):
    rs.on_tick(100_000, qty=10, timestamp=0.0)
    bar = rs.on_tick(100_000, qty=10, timestamp=1.0)
    assert "Bar" in str(bar)
