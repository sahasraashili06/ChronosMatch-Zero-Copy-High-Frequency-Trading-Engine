"""Tests for LatencyProfiler."""
import pytest
from chronosx.latency_profiler import LatencyProfiler, LatencySample, LatencyStats


@pytest.fixture
def prof():
    return LatencyProfiler(alert_multiplier=5.0, max_samples=100)


def test_start_stop_returns_sample(prof):
    prof.start("ev1")
    sample = prof.stop("ev1")
    assert sample is not None
    assert sample.event_id == "ev1"
    assert sample.latency_ns > 0


def test_stop_unknown_returns_none(prof):
    assert prof.stop("nonexistent") is None


def test_sample_count_increments(prof):
    for i in range(5):
        prof.start(f"e{i}"); prof.stop(f"e{i}")
    assert prof.sample_count == 5


def test_pending_count(prof):
    prof.start("a"); prof.start("b")
    assert prof.pending_count == 2
    prof.stop("a")
    assert prof.pending_count == 1


def test_record_ns_direct(prof):
    sample = prof.record_ns("hw_event", 50_000)
    assert sample.latency_ns == 50_000
    assert sample.latency_us == pytest.approx(50.0, abs=0.1)


def test_record_ns_counted(prof):
    for i in range(10):
        prof.record_ns(f"e{i}", 1_000 * (i + 1))
    assert prof.sample_count == 10


def test_stats_none_before_samples(prof):
    assert prof.stats() is None


def test_stats_min_max(prof):
    prof.record_ns("a", 1_000); prof.record_ns("b", 9_000)
    st = prof.stats()
    assert st.min_ns == 1_000
    assert st.max_ns == 9_000


def test_stats_mean(prof):
    for ns in [1_000, 2_000, 3_000]:
        prof.record_ns("x", ns)
    st = prof.stats()
    assert st.mean_ns == pytest.approx(2_000.0, abs=1.0)


def test_stats_p50(prof):
    for i in range(1, 11):
        prof.record_ns(f"e{i}", i * 1_000)
    st = prof.stats()
    assert 5_000 <= st.p50_ns <= 7_000


def test_stats_p99_larger_than_p50(prof):
    for i in range(100):
        prof.record_ns(f"e{i}", (i + 1) * 100)
    st = prof.stats()
    assert st.p99_ns >= st.p50_ns


def test_latency_units(prof):
    prof.record_ns("u", 2_500_000)
    st = prof.stats()
    assert st.mean_us == pytest.approx(2_500.0, abs=1.0)


def test_slow_sample_triggers_alert(prof):
    for _ in range(10):
        prof.record_ns("base", 1_000)
    prof.record_ns("spike", 100_000)
    assert prof.alert_count == 1


def test_normal_samples_no_alert(prof):
    for i in range(20):
        prof.record_ns(f"e{i}", 1_000)
    assert prof.alert_count == 0


def test_reset_clears_all(prof):
    prof.record_ns("x", 1_000)
    prof.reset()
    assert prof.sample_count == 0
    assert prof.stats() is None


def test_invalid_multiplier_raises():
    with pytest.raises(ValueError):
        LatencyProfiler(alert_multiplier=0)


def test_str_sample(prof):
    s = prof.record_ns("test", 50_000)
    assert "LatencySample" in str(s)


def test_summary_string(prof):
    prof.record_ns("x", 1_000)
    assert "Latency" in prof.summary()
