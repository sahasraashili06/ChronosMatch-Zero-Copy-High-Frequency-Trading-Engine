"""Tests for OFICalculator."""
import pytest
from chronosx.ofi import OFICalculator, OFISignal, OFISnapshot


@pytest.fixture
def ofi():
    return OFICalculator(window=5, signal_thresh=0.2)


def _snap(ofi, bp, bq, ap, aq):
    return ofi.update(bid_price=bp, bid_qty=bq, ask_price=ap, ask_qty=aq)


# ---- First tick -------------------------------------------------------------

def test_first_update_returns_snapshot(ofi):
    snap = _snap(ofi, 100_000, 500, 100_100, 300)
    assert isinstance(snap, OFISnapshot)


def test_first_snapshot_has_correct_types(ofi):
    snap = _snap(ofi, 100_000, 500, 100_100, 300)
    assert isinstance(snap.raw, int)
    assert isinstance(snap.normalised, float)
    assert isinstance(snap.signal, OFISignal)


# ---- Buy pressure -----------------------------------------------------------

def test_rising_bid_positive_ofi(ofi):
    _snap(ofi, 100_000, 500, 100_100, 300)
    snap = _snap(ofi, 100_100, 600, 100_100, 300)  # bid lifted
    assert snap.raw > 0


def test_strong_buy_pressure_gives_buy_signal(ofi):
    _snap(ofi, 100_000, 100, 100_200, 1000)
    # large bid increase, ask unchanged → BUY
    snap = _snap(ofi, 100_100, 5000, 100_200, 1000)
    assert snap.signal == OFISignal.BUY


# ---- Sell pressure ----------------------------------------------------------

def test_falling_ask_negative_ofi(ofi):
    _snap(ofi, 100_000, 500, 100_200, 300)
    snap = _snap(ofi, 100_000, 500, 100_100, 800)  # ask dropped with large size
    assert snap.raw < 0


def test_strong_sell_pressure_gives_sell_signal(ofi):
    _snap(ofi, 100_000, 100, 100_200, 100)
    snap = _snap(ofi, 100_000, 100, 100_100, 5000)
    assert snap.signal == OFISignal.SELL


# ---- Normalised bounds ------------------------------------------------------

def test_normalised_bounded_minus_one_to_one(ofi):
    for _ in range(10):
        snap = _snap(ofi, 100_000, 1, 100_100, 99_999)
    assert -1.0 <= snap.normalised <= 1.0


# ---- Rolling ----------------------------------------------------------------

def test_rolling_average_computed(ofi):
    for _ in range(5):
        _snap(ofi, 100_000, 500, 100_100, 300)
    snap = _snap(ofi, 100_100, 600, 100_100, 300)
    assert isinstance(snap.rolling, float)


# ---- Sample count -----------------------------------------------------------

def test_sample_count(ofi):
    for i in range(6):
        _snap(ofi, 100_000 + i * 10, 500, 100_100, 300)
    assert ofi.sample_count == 6


# ---- Reset ------------------------------------------------------------------

def test_reset_clears_state(ofi):
    _snap(ofi, 100_000, 500, 100_100, 300)
    ofi.reset()
    assert ofi.sample_count == 0
    assert ofi.current == 0.0
    assert ofi.signal == OFISignal.NEUTRAL


# ---- Validation -------------------------------------------------------------

def test_invalid_window_raises():
    with pytest.raises(ValueError):
        OFICalculator(window=0)


def test_invalid_thresh_raises():
    with pytest.raises(ValueError):
        OFICalculator(signal_thresh=1.5)


def test_str_representation(ofi):
    _snap(ofi, 100_000, 500, 100_100, 300)
    s = str(ofi)
    assert "OFI" in s
    assert "signal" in s
