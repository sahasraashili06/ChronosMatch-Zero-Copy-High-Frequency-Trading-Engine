"""Tests for DrawdownTracker."""
import pytest
from chronosx.drawdown import DrawdownTracker, DrawdownEvent


@pytest.fixture
def dd():
    return DrawdownTracker(initial_equity=100_000.0, alert_pct=5.0)


def test_no_drawdown_at_start(dd):
    assert dd.current_drawdown == 0.0
    assert dd.current_pct == 0.0
    assert dd.is_in_drawdown is False


def test_equity_above_peak_no_drawdown(dd):
    dd.update(105_000)
    assert dd.current_drawdown == 0.0
    assert dd.is_in_drawdown is False
    assert dd.peak == 105_000.0


def test_simple_drawdown(dd):
    dd.update(95_000)
    assert dd.current_drawdown == pytest.approx(-5_000.0)
    assert dd.current_pct == pytest.approx(-5.0, abs=1e-6)
    assert dd.is_in_drawdown is True


def test_max_drawdown_tracked(dd):
    dd.update(95_000)
    dd.update(97_000)   # partial recovery
    assert dd.max_drawdown     == pytest.approx(-5_000.0)
    assert dd.max_drawdown_pct == pytest.approx(-5.0, abs=1e-6)


def test_new_peak_resets_duration(dd):
    dd.update(95_000)
    assert dd.duration == 1
    dd.update(105_000)  # new peak
    assert dd.duration == 0


def test_duration_increments(dd):
    dd.update(95_000)
    dd.update(94_000)
    dd.update(93_000)
    assert dd.duration == 3


def test_alert_fired_above_threshold(dd):
    event = dd.update(94_000)   # -6% > -5% threshold
    assert event is not None
    assert event.pct < -5.0
    assert dd.alert_count == 1


def test_no_alert_below_threshold(dd):
    event = dd.update(97_000)   # -3% < -5% threshold
    assert event is None
    assert dd.alert_count == 0


def test_reset_clears_state(dd):
    dd.update(90_000)
    dd.reset(new_equity=100_000.0)
    assert dd.peak   == 100_000.0
    assert dd.equity == 100_000.0
    assert dd.max_drawdown == 0.0
    assert dd.alert_count  == 0
    assert dd.duration     == 0


def test_sample_count(dd):
    for _ in range(5):
        dd.update(99_000)
    assert dd.sample_count == 5


def test_invalid_alert_pct_raises():
    with pytest.raises(ValueError):
        DrawdownTracker(alert_pct=0)


def test_str_representation(dd):
    dd.update(95_000)
    s = str(dd)
    assert "DrawdownTracker" in s
    assert "peak" in s
