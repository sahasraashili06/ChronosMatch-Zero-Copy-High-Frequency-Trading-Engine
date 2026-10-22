"""Tests for TokenBucket / MultiLevelThrottle"""
import time
import pytest
from chronosx.throttle import TokenBucket, MultiLevelThrottle, ThrottleStats


def test_full_bucket_allows_first_consume():
    tb = TokenBucket(rate=10, capacity=10)
    assert tb.consume() is True
    assert tb.stats.allowed == 1


def test_empty_bucket_rejects():
    tb = TokenBucket(rate=1, capacity=3)
    tb.consume(); tb.consume(); tb.consume()   # drain
    result = tb.consume()   # should be rejected
    assert result is False
    assert tb.stats.rejected == 1


def test_stats_counts_correctly():
    tb = TokenBucket(rate=5, capacity=3)
    for _ in range(3):
        tb.consume()
    tb.consume()   # rejected
    assert tb.stats.allowed  == 3
    assert tb.stats.rejected == 1
    assert tb.stats.total    == 4


def test_reject_rate():
    tb = TokenBucket(rate=10, capacity=2)
    tb.consume(); tb.consume()     # 2 allowed
    tb.consume()                   # 1 rejected
    assert tb.stats.reject_rate == pytest.approx(1/3, abs=1e-6)


def test_refill_over_time():
    tb = TokenBucket(rate=1000, capacity=100)
    # Drain completely
    for _ in range(100):
        tb.consume()
    time.sleep(0.02)   # 20ms → should refill ~20 tokens
    assert tb.available() >= 15


def test_capacity_not_exceeded():
    tb = TokenBucket(rate=10_000, capacity=50)
    time.sleep(0.01)
    assert tb.available() <= 50


def test_reset_refills_bucket():
    tb = TokenBucket(rate=1, capacity=5)
    for _ in range(5):
        tb.consume()
    assert tb.consume() is False
    tb.reset()
    assert tb.consume() is True


def test_multi_level_allows_within_limits():
    mlt = MultiLevelThrottle(per_sec=100, per_min=1000)
    assert mlt.consume() is True


def test_multi_level_rejects_when_second_bucket_empty():
    mlt = MultiLevelThrottle(per_sec=2, per_min=10_000)
    mlt.consume(); mlt.consume()   # drain per-sec
    assert mlt.consume() is False


def test_invalid_rate_raises():
    with pytest.raises(ValueError):
        TokenBucket(rate=0, capacity=10)


def test_invalid_capacity_raises():
    with pytest.raises(ValueError):
        TokenBucket(rate=10, capacity=0)
