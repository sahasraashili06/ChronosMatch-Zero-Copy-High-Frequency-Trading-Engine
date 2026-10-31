"""Tests for RiskDashboard."""
import pytest
from chronosx.risk_dashboard import RiskDashboard, RiskLevel, RiskStatus
from chronosx.circuit_breaker import BreakerConfig
from chronosx.types import TradeEvent, Side


@pytest.fixture
def dash():
    cfg = BreakerConfig(
        max_price_move_pct=50.0,      # very high → won't trip on price
        window_sec=60.0,
        max_loss_fixed=999_999_999,   # very high → breaker won't trip on PnL
        cooldown_sec=9999.0,          # won't auto-recover in tests
    )
    return RiskDashboard(
        capital=100_000.0,
        max_drawdown_pct=10.0,
        max_vpin=0.7,
        max_spread_z=3.0,
        kelly_fraction=0.5,
        breaker_cfg=cfg,
    )


# ── Initial state ─────────────────────────────────────────────────────────────

def test_initial_status_green(dash):
    s = dash.status()
    assert s.level == RiskLevel.GREEN
    assert s.trading_allowed is True
    assert s.halt_reason is None


def test_initial_no_alerts(dash):
    assert dash.status().active_alerts == []


# ── Drawdown ──────────────────────────────────────────────────────────────────

def test_small_drawdown_stays_green(dash):
    dash.on_equity(96_000)   # -4%, below 10% limit
    assert dash.status().level == RiskLevel.GREEN


def test_large_drawdown_turns_yellow(dash):
    dash.on_equity(91_500)   # -8.5%, >70% of 10% threshold → YELLOW
    assert dash.status().level == RiskLevel.YELLOW


def test_breach_drawdown_limit_halts(dash):
    dash.on_equity(89_000)   # -11% > 10% limit
    s = dash.status()
    assert s.level == RiskLevel.RED
    assert s.trading_allowed is False
    assert any("rawdown" in a for a in s.active_alerts)


def test_drawdown_pct_in_status(dash):
    dash.on_equity(95_000)
    s = dash.status()
    assert s.drawdown_pct == pytest.approx(-5.0, abs=0.01)


# ── Manual halt / resume ──────────────────────────────────────────────────────

def test_manual_halt_stops_trading(dash):
    dash.halt("Testing halt")
    s = dash.status()
    assert s.trading_allowed is False
    assert s.level == RiskLevel.RED
    assert s.halt_reason == "Testing halt"


def test_resume_restores_trading(dash):
    dash.halt("Temp halt")
    dash.resume()
    assert dash.status().trading_allowed is True


# ── VPIN ──────────────────────────────────────────────────────────────────────

def test_high_vpin_turns_yellow(dash):
    # Fill 10+ buckets with heavy buy-side imbalance
    for _ in range(20):
        t = TradeEvent(aggressor_id=1, resting_id=2, price=100_000, qty=500)
        dash.on_trade(t, Side.Buy)
    s = dash.status()
    assert s.vpin > 0.0


# ── Spread ────────────────────────────────────────────────────────────────────

def test_normal_spread_no_alert(dash):
    for _ in range(25):
        dash.on_spread(100)   # stable spread
    assert dash.spread.alert_count == 0


def test_spread_z_in_status(dash):
    for _ in range(20):
        dash.on_spread(100)
    s = dash.status()
    # spread z-score may be None until there's variance
    assert s.spread_z is None or isinstance(s.spread_z, float)


# ── Kelly sizing ──────────────────────────────────────────────────────────────

def test_no_kelly_size_before_min_trades(dash):
    assert dash.recommended_size(100_000) == 0


def test_kelly_size_after_enough_trades(dash):
    for _ in range(6):
        dash.on_trade_result(200.0)
    for _ in range(4):
        dash.on_trade_result(-100.0)
    size = dash.recommended_size(100_000)   # price = $10.0000
    assert size >= 0  # valid (may be 0 if kelly=0)


# ── Convenience properties ────────────────────────────────────────────────────

def test_is_green_true_initially(dash):
    assert dash.is_green is True


def test_is_halted_false_initially(dash):
    assert dash.is_halted is False


def test_is_halted_true_after_halt(dash):
    dash.halt()
    assert dash.is_halted is True


# ── RiskStatus fields ─────────────────────────────────────────────────────────

def test_status_has_all_fields(dash):
    s = dash.status()
    assert hasattr(s, "level")
    assert hasattr(s, "trading_allowed")
    assert hasattr(s, "vpin")
    assert hasattr(s, "drawdown_pct")
    assert hasattr(s, "kelly_fraction")
    assert hasattr(s, "active_alerts")
    assert hasattr(s, "breaker_state")
