"""Tests for FeeCalculator."""
import pytest
from chronosx.fee_calculator import FeeCalculator, FeeResult, FeeTier
from chronosx.types import PRICE_MULT


@pytest.fixture
def calc():
    return FeeCalculator(maker_bps=2.0, taker_bps=5.0)


# ---- Basic fee computation --------------------------------------------------

def test_taker_fee_correct(calc):
    # $1000 notional @ 5bps = $0.50
    result = calc.compute(notional=10_000_000, is_maker=False)
    assert result.fee_usd == pytest.approx(0.50, abs=1e-4)


def test_maker_fee_correct(calc):
    # $1000 notional @ 2bps = $0.20
    result = calc.compute(notional=10_000_000, is_maker=True)
    assert result.fee_usd == pytest.approx(0.20, abs=1e-4)


def test_net_notional(calc):
    result = calc.compute(notional=10_000_000, is_maker=False)
    expected_net = result.notional_usd - result.fee_usd
    assert result.net_notional_usd == pytest.approx(expected_net, abs=1e-4)


def test_from_price_qty(calc):
    # 100 shares @ $10.00 = $1000 notional
    result = calc.compute_from_price_qty(price=100_000, qty=100, is_maker=False)
    assert result.notional_usd == pytest.approx(1000.0, abs=0.01)
    assert result.fee_usd      == pytest.approx(0.50,   abs=1e-4)


# ---- Tiered fees ------------------------------------------------------------

def test_tier_applied_at_volume():
    tiers = [FeeTier(min_volume_usd=100_000, maker_bps=1.0, taker_bps=3.0)]
    calc  = FeeCalculator(maker_bps=2.0, taker_bps=5.0, tiers=tiers, volume_30d=200_000)
    result = calc.compute(notional=10_000_000, is_maker=False)
    assert result.bps_applied == 3.0


def test_default_fee_below_tier():
    tiers = [FeeTier(min_volume_usd=100_000, maker_bps=1.0, taker_bps=3.0)]
    calc  = FeeCalculator(maker_bps=2.0, taker_bps=5.0, tiers=tiers, volume_30d=50_000)
    result = calc.compute(notional=10_000_000, is_maker=False)
    assert result.bps_applied == 5.0


def test_set_volume_30d(calc):
    calc.set_volume_30d(500_000)
    assert calc._volume_30d == 500_000


# ---- Running totals ---------------------------------------------------------

def test_total_fees_accumulated(calc):
    calc.compute(notional=10_000_000, is_maker=False)
    calc.compute(notional=10_000_000, is_maker=False)
    assert calc.total_fees_usd == pytest.approx(1.00, abs=1e-4)


def test_fill_count(calc):
    calc.compute(notional=10_000_000, is_maker=False)
    calc.compute(notional=10_000_000, is_maker=True)
    assert calc.fill_count == 2


def test_reset_stats(calc):
    calc.compute(notional=10_000_000, is_maker=False)
    calc.reset_stats()
    assert calc.fill_count      == 0
    assert calc.total_fees_usd  == 0.0


# ---- Effective bps properties -----------------------------------------------

def test_effective_maker_bps(calc):
    assert calc.effective_maker_bps == 2.0


def test_effective_taker_bps(calc):
    assert calc.effective_taker_bps == 5.0


# ---- FeeResult str ----------------------------------------------------------

def test_str_representation(calc):
    r = calc.compute(notional=10_000_000, is_maker=False)
    s = str(r)
    assert "taker" in s
    assert "fee" in s
