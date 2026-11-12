"""Tests for BarBuilder (OHLCV)."""
import pytest
from chronosx.bar_builder import BarBuilder, BarType, OhlcvBar
from chronosx.types import TradeEvent


def _t(price: int, qty: int = 10) -> TradeEvent:
    return TradeEvent(aggressor_id=1, resting_id=2, price=price, qty=qty)


# ── Tick bars ─────────────────────────────────────────────────────────────────

def test_tick_bar_closes_at_size():
    bb = BarBuilder(BarType.Tick, size=3)
    assert bb.on_trade(_t(100_000)) is None
    assert bb.on_trade(_t(101_000)) is None
    bar = bb.on_trade(_t(102_000))
    assert bar is not None
    assert bb.bar_count == 1


def test_tick_bar_ohlc():
    bb = BarBuilder(BarType.Tick, size=3)
    bb.on_trade(_t(100_000))
    bb.on_trade(_t(105_000))
    bar = bb.on_trade(_t(98_000))
    assert bar.open  == 100_000
    assert bar.high  == 105_000
    assert bar.low   == 98_000
    assert bar.close == 98_000


def test_tick_bar_volume():
    bb = BarBuilder(BarType.Tick, size=2)
    bb.on_trade(_t(100_000, qty=30))
    bar = bb.on_trade(_t(100_000, qty=20))
    assert bar.volume == 50
    assert bar.tick_count == 2


# ── Volume bars ───────────────────────────────────────────────────────────────

def test_volume_bar_closes_at_size():
    bb = BarBuilder(BarType.Volume, size=100)
    assert bb.on_trade(_t(100_000, qty=50)) is None
    bar = bb.on_trade(_t(100_000, qty=50))
    assert bar is not None


def test_volume_bar_accumulates_correctly():
    bb = BarBuilder(BarType.Volume, size=100)
    bb.on_trade(_t(100_000, qty=40))
    bb.on_trade(_t(102_000, qty=30))
    bar = bb.on_trade(_t(99_000, qty=30))
    assert bar.volume == 100
    assert bar.high   == 102_000
    assert bar.low    == 99_000


# ── VWAP ──────────────────────────────────────────────────────────────────────

def test_vwap_single_price():
    bb = BarBuilder(BarType.Tick, size=2)
    bb.on_trade(_t(100_000, qty=50))
    bar = bb.on_trade(_t(100_000, qty=50))
    assert bar.vwap == pytest.approx(100_000 / 10_000, abs=1e-4)  # $10.0000


def test_vwap_weighted():
    bb = BarBuilder(BarType.Tick, size=2)
    bb.on_trade(_t(100_000, qty=100))   # 100 @ $10
    bar = bb.on_trade(_t(200_000, qty=100))  # 100 @ $20
    assert bar.vwap == pytest.approx(15.0, abs=0.001)  # avg = $15


# ── Flush ─────────────────────────────────────────────────────────────────────

def test_flush_partial_bar():
    bb = BarBuilder(BarType.Tick, size=5)
    bb.on_trade(_t(100_000))
    bar = bb.flush()
    assert bar is not None
    assert bar.tick_count == 1


def test_flush_empty_returns_none():
    bb = BarBuilder(BarType.Tick, size=5)
    assert bb.flush() is None


# ── General ───────────────────────────────────────────────────────────────────

def test_completed_bars_list():
    bb = BarBuilder(BarType.Tick, size=2)
    bb.on_trade(_t(100_000)); bb.on_trade(_t(101_000))
    bb.on_trade(_t(102_000)); bb.on_trade(_t(103_000))
    assert bb.bar_count == 2
    assert len(bb.completed_bars) == 2


def test_current_bar_snapshot():
    bb = BarBuilder(BarType.Tick, size=5)
    bb.on_trade(_t(100_000, qty=20))
    snap = bb.current_bar
    assert snap is not None
    assert snap["volume"] == 20
    assert snap["ticks"]  == 1


def test_invalid_size_raises():
    with pytest.raises(ValueError):
        BarBuilder(BarType.Tick, size=0)


def test_str_representation():
    bb = BarBuilder(BarType.Volume, size=100)
    bb.on_trade(_t(100_000, qty=50))
    bar = bb.on_trade(_t(100_000, qty=50))
    s = str(bar)
    assert "Bar[Volume]" in s
    assert "VWAP" in s
