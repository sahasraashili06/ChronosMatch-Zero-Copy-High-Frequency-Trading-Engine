"""Tests for KellySizer."""
import pytest
from chronosx.kelly_sizer import KellySizer, KellyStats


def _feed(ks, wins, losses):
    for w in wins:
        ks.record_trade(w)
    for l in losses:
        ks.record_trade(-l)


@pytest.fixture
def ks():
    return KellySizer(capital=100_000.0, fraction=0.5, min_trades=5)


def test_no_recommendation_before_min_trades(ks):
    ks.record_trade(100)
    assert ks.kelly_fraction()       is None
    assert ks.recommended_fraction() is None
    assert ks.position_size(100_000) is None


def test_kelly_fraction_positive_edge(ks):
    # Perfect win rate with equal win/loss → kelly = 1 - 0/R = 1.0 (clamped)
    _feed(ks, [100]*5, [100]*0)   # only wins — but no losses → None
    assert ks.kelly_fraction() is None


def test_kelly_fraction_with_wins_and_losses(ks):
    _feed(ks, [200, 200, 200], [100, 100])
    # W=0.6, avg_win=200, avg_loss=100 → R=2 → kelly=0.6 - 0.4/2 = 0.4
    k = ks.kelly_fraction()
    assert k is not None
    assert k == pytest.approx(0.4, abs=1e-6)


def test_recommended_fraction_is_half_kelly(ks):
    _feed(ks, [200, 200, 200], [100, 100])
    rf = ks.recommended_fraction()
    assert rf is not None
    assert rf == pytest.approx(0.2, abs=1e-6)   # 0.4 × 0.5


def test_position_size_shares(ks):
    _feed(ks, [200, 200, 200], [100, 100])
    # capital=100k, fraction=0.2 → $20k at risk, price=$10 → 2000 shares
    size = ks.position_size(100_000)   # $10.0000
    assert size == 2000


def test_position_size_usd(ks):
    _feed(ks, [200, 200, 200], [100, 100])
    usd = ks.position_size_usd()
    assert usd == pytest.approx(20_000.0, abs=1.0)


def test_kelly_clamped_to_zero_on_negative(ks):
    # More losses than wins → kelly goes negative → clamped to 0
    _feed(ks, [50]*2, [200]*3)
    k = ks.kelly_fraction()
    assert k is not None
    assert k == 0.0


def test_trade_count(ks):
    ks.record_trade(100)
    ks.record_trade(-50)
    ks.record_trade(200)
    assert ks.trade_count == 3
    assert ks.win_count   == 2
    assert ks.loss_count  == 1


def test_reset_clears_trades(ks):
    _feed(ks, [100]*5, [50]*5)
    ks.reset()
    assert ks.trade_count == 0
    assert ks.kelly_fraction() is None


def test_fixed_point_recording(ks):
    for _ in range(3):
        ks.record_trade_fixed(2_000_000)   # $200
    for _ in range(2):
        ks.record_trade_fixed(-1_000_000)  # -$100
    k = ks.kelly_fraction()
    assert k == pytest.approx(0.4, abs=1e-6)


def test_stats_returned_after_min_trades(ks):
    _feed(ks, [200]*3, [100]*2)
    st = ks.stats()
    assert st is not None
    assert isinstance(st, KellyStats)
    assert st.win_rate == pytest.approx(0.6, abs=1e-6)


def test_invalid_fraction_raises():
    with pytest.raises(ValueError):
        KellySizer(fraction=0.0)


def test_invalid_capital_raises():
    with pytest.raises(ValueError):
        KellySizer(capital=-1000.0)


def test_update_capital(ks):
    ks.update_capital(200_000.0)
    assert ks.capital == 200_000.0
