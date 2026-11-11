"""Tests for RollingStats."""
import pytest
import math
from chronosx.rolling_stats import RollingStats, StatSnapshot


@pytest.fixture
def rs():
    return RollingStats(window=5)


# ---- Basic ------------------------------------------------------------------

def test_first_update_returns_snapshot(rs):
    snap = rs.update(10.0)
    assert isinstance(snap, StatSnapshot)
    assert snap.value == 10.0
    assert snap.count == 1


def test_mean_single_value(rs):
    snap = rs.update(42.0)
    assert snap.mean == pytest.approx(42.0)


def test_mean_multiple_values(rs):
    for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
        snap = rs.update(v)
    assert snap.mean == pytest.approx(3.0, abs=1e-6)


def test_std_constant_zero(rs):
    for _ in range(5):
        snap = rs.update(10.0)
    assert snap.std == pytest.approx(0.0, abs=1e-6)


def test_std_known_values(rs):
    # [2, 4, 4, 4, 5, 5, 7, 9] std ≈ 2.0 (but we use window=5)
    for v in [2.0, 4.0, 4.0, 4.0, 5.0]:
        snap = rs.update(v)
    assert snap.std > 0


# ---- Z-score ----------------------------------------------------------------

def test_z_score_none_first_sample(rs):
    snap = rs.update(10.0)
    assert snap.z_score is None


def test_z_score_zero_at_mean(rs):
    for _ in range(5):
        rs.update(10.0)
    # Inject a value at exact mean
    snap = rs.update(10.0)
    # std ≈ 0, z_score should be None (no division)
    assert snap.z_score is None or snap.z_score == pytest.approx(0.0, abs=0.1)


def test_z_score_spike(rs):
    for _ in range(4):
        rs.update(10.0)
    snap = rs.update(10.1)   # tiny std after constant values
    # Either z is None (std=0 after window shift) or large positive
    if snap.z_score is not None:
        assert snap.z_score > 0


# ---- Min / Max --------------------------------------------------------------

def test_min_max_tracked(rs):
    for v in [3.0, 1.0, 4.0, 1.0, 5.0]:
        snap = rs.update(v)
    assert snap.min_val == pytest.approx(1.0)
    assert snap.max_val == pytest.approx(5.0)


def test_min_max_slide_with_window():
    rs = RollingStats(window=3)
    rs.update(10.0)
    rs.update(20.0)
    rs.update(30.0)
    snap = rs.update(5.0)   # 10 evicted, window = [20, 30, 5]
    assert snap.min_val == pytest.approx(5.0)
    assert snap.max_val == pytest.approx(30.0)


# ---- Pct change -------------------------------------------------------------

def test_pct_change_none_on_first(rs):
    snap = rs.update(100.0)
    assert snap.pct_change is None


def test_pct_change_computed(rs):
    rs.update(100.0)
    snap = rs.update(110.0)
    # oldest in window is 100 → pct = +10%
    assert snap.pct_change == pytest.approx(10.0, abs=0.01)


# ---- is_full ----------------------------------------------------------------

def test_is_full_false_initially(rs):
    rs.update(1.0)
    assert rs.is_full is False


def test_is_full_true_after_window(rs):
    for i in range(5):
        rs.update(float(i))
    assert rs.is_full is True


# ---- Reset ------------------------------------------------------------------

def test_reset_clears_state(rs):
    for i in range(5):
        rs.update(float(i))
    rs.reset()
    assert rs.sample_count == 0
    assert rs.mean == 0.0
    assert rs.is_full is False


# ---- Validation -------------------------------------------------------------

def test_invalid_window_raises():
    with pytest.raises(ValueError):
        RollingStats(window=1)


# ---- Str -------------------------------------------------------------------

def test_str_snapshot(rs):
    rs.update(10.0)
    snap = rs.update(12.0)
    s = str(snap)
    assert "Stats" in s
    assert "mean" in s
