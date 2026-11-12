"""Tests for SpreadMonitor."""
import pytest
from chronosx.spread_monitor import SpreadMonitor, SpreadAlert


@pytest.fixture
def mon():
    return SpreadMonitor(z_threshold=2.0, min_samples=5)


def test_initial_no_spread(mon):
    assert mon.current_spread is None
    assert mon.sample_count == 0


def test_warming_up_no_alert(mon):
    for i in range(4):
        alert = mon.update_raw(100)
        assert alert is None


def test_normal_spread_no_alert(mon):
    for _ in range(10):
        alert = mon.update_raw(100)   # all same → std=0, no alert
    assert alert is None
    assert mon.alert_count == 0


def test_spike_triggers_alert(mon):
    for _ in range(10):
        mon.update_raw(100)
    alert = mon.update_raw(10_000)   # massive spike
    assert alert is not None
    assert alert.z_score > 2.0


def test_alert_recorded(mon):
    for _ in range(10):
        mon.update_raw(100)
    mon.update_raw(50_000)
    assert mon.alert_count == 1


def test_mean_computed(mon):
    for _ in range(10):
        mon.update_raw(200)
    assert mon.mean == pytest.approx(200.0, abs=1e-6)


def test_std_zero_for_constant_spread(mon):
    for _ in range(10):
        mon.update_raw(150)
    assert mon.std == pytest.approx(0.0, abs=1e-6)


def test_z_score_none_before_min_samples(mon):
    mon.update_raw(100)
    assert mon.z_score is None


def test_is_wide_false_normally(mon):
    for _ in range(10):
        mon.update_raw(100)
    assert mon.is_wide() is False


def test_is_wide_true_on_spike(mon):
    for _ in range(10):
        mon.update_raw(100)
    mon.update_raw(99_999)
    assert mon.is_wide() is True


def test_reset_clears_state(mon):
    for _ in range(10):
        mon.update_raw(100)
    mon.reset()
    assert mon.sample_count == 0
    assert mon.current_spread is None
    assert mon.alert_count == 0


def test_sample_count_increments(mon):
    for i in range(7):
        mon.update_raw(100)
    assert mon.sample_count == 7
