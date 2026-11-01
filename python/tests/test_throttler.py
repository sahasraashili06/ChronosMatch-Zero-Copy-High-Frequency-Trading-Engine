"""Tests for TradeThrottler."""
import time
import pytest
from chronosx.throttler import TradeThrottler, ThrottleStatus


@pytest.fixture
def throttle():
    # Large capacity so tests don't hit the rate limit accidentally
    return TradeThrottler(rate=1000.0, capacity=20.0, max_consec_rej=3, cooldown_sec=1.0)


# ---- Basic allow/deny -------------------------------------------------------

def test_first_order_allowed(throttle):
    assert throttle.allow() is True


def test_tokens_consumed(throttle):
    before = throttle.tokens
    throttle.allow()
    assert throttle.tokens < before


def test_total_counters(throttle):
    throttle.allow()
    throttle.allow()
    assert throttle.total_allowed == 2
    assert throttle.total_rejected == 0


# ---- Token bucket exhaustion ------------------------------------------------

def test_burst_exhausts_tokens():
    th = TradeThrottler(rate=0.01, capacity=3.0)   # very slow refill
    # Drain all 3 tokens
    assert th.allow() is True
    assert th.allow() is True
    assert th.allow() is True
    # 4th should be rejected
    assert th.allow() is False
    assert th.total_rejected == 1


def test_reject_reason_set_on_denial():
    th = TradeThrottler(rate=0.01, capacity=1.0)
    th.allow()                  # drain
    th.allow()                  # rejected
    assert th.reject_reason is not None
    assert "Rate limit" in th.reject_reason


# ---- Notional cap -----------------------------------------------------------

def test_notional_cap_blocks_order(throttle):
    throttle2 = TradeThrottler(rate=1000.0, capacity=20.0,
                               max_notional=100_000, max_consec_rej=99)
    throttle2.allow(order_notional=90_000)
    result = throttle2.allow(order_notional=20_000)  # 90k+20k > 100k
    assert result is False
    assert "Notional" in throttle2.reject_reason


def test_notional_within_cap_allowed(throttle):
    throttle2 = TradeThrottler(rate=1000.0, capacity=20.0,
                               max_notional=100_000, max_consec_rej=99)
    assert throttle2.allow(order_notional=40_000) is True
    assert throttle2.allow(order_notional=40_000) is True


# ---- Consecutive reject cooldown --------------------------------------------

def test_consec_rej_triggers_cooldown():
    th = TradeThrottler(rate=0.001, capacity=1.0, max_consec_rej=2, cooldown_sec=10.0)
    th.allow()       # drain token
    th.allow()       # reject 1
    th.allow()       # reject 2 → cooldown
    assert th.is_cooling_down() is True


def test_no_cooldown_initially(throttle):
    assert throttle.is_cooling_down() is False


# ---- Status snapshot --------------------------------------------------------

def test_status_allowed(throttle):
    st = throttle.status()
    assert isinstance(st, ThrottleStatus)
    assert st.allowed is True
    assert st.tokens_left > 0


def test_status_notional_used(throttle):
    th = TradeThrottler(rate=1000.0, capacity=20.0, max_notional=1_000_000)
    th.allow(order_notional=50_000)
    st = th.status()
    assert st.notional_used == 50_000


# ---- Reset ------------------------------------------------------------------

def test_reset_restores_tokens(throttle):
    throttle.allow(); throttle.allow(); throttle.allow()
    throttle.reset()
    assert throttle.tokens == pytest.approx(20.0, abs=0.1)


def test_reset_clears_counters(throttle):
    throttle.allow(); throttle.allow()
    throttle.reset()
    assert throttle.total_allowed  == 0
    assert throttle.total_rejected == 0


# ---- Validation -------------------------------------------------------------

def test_invalid_rate_raises():
    with pytest.raises(ValueError):
        TradeThrottler(rate=0)


def test_invalid_capacity_raises():
    with pytest.raises(ValueError):
        TradeThrottler(capacity=-1)
