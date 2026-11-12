"""Tests for MarketImpactEstimator."""
import math
import pytest
from chronosx.market_impact import MarketImpactEstimator, ImpactResult, SliceImpact


@pytest.fixture
def est():
    return MarketImpactEstimator(eta=0.1, gamma=0.05, sigma=0.02, adv=1_000_000)


# ---- Basic structure --------------------------------------------------------

def test_estimate_returns_result(est):
    result = est.estimate(qty=10_000, mid_price=100_000, num_slices=5)
    assert isinstance(result, ImpactResult)


def test_num_slices_match(est):
    result = est.estimate(qty=10_000, mid_price=100_000, num_slices=5)
    assert len(result.slices) == 5
    assert result.num_slices == 5


def test_total_qty_correct(est):
    result = est.estimate(qty=10_003, mid_price=100_000, num_slices=5)
    assert sum(s.qty for s in result.slices) == 10_003


def test_slice_qty_distributed(est):
    result = est.estimate(qty=100, mid_price=100_000, num_slices=4)
    # 100 / 4 = 25 each, no remainder
    assert all(s.qty == 25 for s in result.slices)


def test_remainder_distributed_to_first_slices(est):
    result = est.estimate(qty=103, mid_price=100_000, num_slices=5)
    qtys = [s.qty for s in result.slices]
    # First 3 slices get 21, rest get 20
    assert sum(qtys) == 103
    assert max(qtys) - min(qtys) <= 1


# ---- Impact values ----------------------------------------------------------

def test_temp_impact_positive(est):
    result = est.estimate(qty=50_000, mid_price=100_000)
    for s in result.slices:
        assert s.temp_impact >= 0


def test_perm_impact_positive(est):
    result = est.estimate(qty=50_000, mid_price=100_000)
    assert result.total_perm >= 0


def test_larger_order_higher_impact(est):
    r_small = est.estimate(qty=1_000,  mid_price=100_000, num_slices=5)
    r_large = est.estimate(qty=100_000, mid_price=100_000, num_slices=5)
    assert r_large.total_cost_usd > r_small.total_cost_usd


def test_execution_price_above_mid(est):
    result = est.estimate(qty=50_000, mid_price=100_000)
    # For a buy order with positive impact, exec prices should trend above mid
    for s in result.slices:
        assert s.execution_price >= 100_000


# ---- USD conversions --------------------------------------------------------

def test_total_cost_usd_non_negative(est):
    result = est.estimate(qty=10_000, mid_price=100_000, num_slices=10)
    assert result.total_cost_usd >= 0.0


def test_avg_slippage_less_than_total(est):
    result = est.estimate(qty=10_000, mid_price=100_000, num_slices=10)
    assert result.avg_slippage_usd <= result.total_cost_usd


def test_impact_bps_positive(est):
    result = est.estimate(qty=50_000, mid_price=100_000, num_slices=10)
    assert result.impact_bps >= 0.0


# ---- Participation rate -----------------------------------------------------

def test_participation_rate(est):
    rate = est.participation_rate(qty=100_000, duration_days=1.0)
    assert rate == pytest.approx(0.1, abs=1e-9)


def test_breakeven_spread_positive(est):
    bep = est.breakeven_spread_bps(qty=50_000, mid_price=100_000)
    assert bep >= 0.0


# ---- Edge cases & validation ------------------------------------------------

def test_single_slice(est):
    result = est.estimate(qty=1000, mid_price=100_000, num_slices=1)
    assert len(result.slices) == 1
    assert result.slices[0].qty == 1000


def test_invalid_qty_raises(est):
    with pytest.raises(ValueError):
        est.estimate(qty=0, mid_price=100_000)


def test_invalid_num_slices_raises(est):
    with pytest.raises(ValueError):
        est.estimate(qty=1000, mid_price=100_000, num_slices=0)


def test_invalid_adv_raises():
    with pytest.raises(ValueError):
        MarketImpactEstimator(adv=0)


def test_zero_sigma_no_crash():
    est0 = MarketImpactEstimator(sigma=0.0, adv=1_000_000)
    result = est0.estimate(qty=1000, mid_price=100_000, num_slices=5)
    assert result.total_cost_usd == 0.0


# ---- Str representation -----------------------------------------------------

def test_str_impact_result(est):
    result = est.estimate(qty=10_000, mid_price=100_000)
    s = str(result)
    assert "ImpactResult" in s
    assert "bps" in s
