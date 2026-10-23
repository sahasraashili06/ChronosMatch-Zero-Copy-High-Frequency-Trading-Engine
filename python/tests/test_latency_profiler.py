"""Tests for LatencyProfiler"""
import time
import pytest
from chronosx.latency_profiler import LatencyProfiler, LatencyStats


@pytest.fixture
def prof():
    return LatencyProfiler()


def test_no_samples_returns_none(prof):
    assert prof.stats("missing") is None
    assert prof.percentile("missing", 50) is None


def test_context_manager_records_sample(prof):
    with prof.measure("op"):
        time.sleep(0.001)   # 1ms
    assert prof.sample_count("op") == 1


def test_manual_record(prof):
    t0 = prof.start()
    time.sleep(0.0001)
    elapsed = prof.record("op", t0)
    assert elapsed > 0
    assert prof.sample_count("op") == 1


def test_add_sample(prof):
    prof.add_sample("op", 500)
    prof.add_sample("op", 1000)
    assert prof.sample_count("op") == 2


def test_stats_computed_correctly(prof):
    for ns in [100, 200, 300, 400, 500]:
        prof.add_sample("op", ns)
    st = prof.stats("op")
    assert st is not None
    assert st.count   == 5
    assert st.min_ns  == 100
    assert st.max_ns  == 500
    assert st.mean_ns == 300.0


def test_p50_in_range(prof):
    for i in range(1, 101):
        prof.add_sample("op", i * 100)
    p50 = prof.percentile("op", 50)
    assert p50 is not None
    assert 4900 <= p50 <= 5100


def test_p99_higher_than_p50(prof):
    for i in range(100):
        prof.add_sample("op", i)
    p50 = prof.percentile("op", 50)
    p99 = prof.percentile("op", 99)
    assert p99 > p50  # type: ignore


def test_multiple_operations_tracked_separately(prof):
    prof.add_sample("submit", 1000)
    prof.add_sample("cancel", 500)
    assert prof.sample_count("submit") == 1
    assert prof.sample_count("cancel") == 1


def test_reset_single_op(prof):
    prof.add_sample("op", 100)
    prof.reset("op")
    assert prof.sample_count("op") == 0


def test_reset_all(prof):
    prof.add_sample("a", 100)
    prof.add_sample("b", 200)
    prof.reset()
    assert prof.all_names() == []


def test_report_string_not_empty(prof):
    prof.add_sample("op", 1000)
    r = prof.report("op")
    assert "op" in r
    assert "n=1" in r
