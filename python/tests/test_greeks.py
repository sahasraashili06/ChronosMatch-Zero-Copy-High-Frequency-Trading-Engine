"""Tests for BSGreeks (Black-Scholes option pricer + Greeks)."""
import math
import pytest
from chronosx.greeks import BSGreeks, GreeksSnapshot, _norm_cdf, _norm_pdf


# ---- Normal distribution helpers -------------------------------------------

def test_norm_cdf_at_zero():
    assert _norm_cdf(0.0) == pytest.approx(0.5, abs=1e-6)

def test_norm_cdf_large_positive():
    assert _norm_cdf(10.0) == pytest.approx(1.0, abs=1e-6)

def test_norm_cdf_large_negative():
    assert _norm_cdf(-10.0) == pytest.approx(0.0, abs=1e-6)

def test_norm_pdf_at_zero():
    assert _norm_pdf(0.0) == pytest.approx(1.0 / math.sqrt(2 * math.pi), rel=1e-6)


# ---- Fixtures ---------------------------------------------------------------

@pytest.fixture
def atm():
    """ATM call: S=K=100, T=1yr, r=5%, sigma=20%."""
    return BSGreeks(S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20)

@pytest.fixture
def itm():
    """Deep ITM call."""
    return BSGreeks(S=120.0, K=100.0, T=0.5, r=0.05, sigma=0.20)

@pytest.fixture
def otm():
    """Deep OTM call."""
    return BSGreeks(S=80.0, K=100.0, T=0.5, r=0.05, sigma=0.20)


# ---- Pricing ----------------------------------------------------------------

def test_call_price_positive(atm):
    assert atm.price("call") > 0

def test_put_price_positive(atm):
    assert atm.price("put") > 0

def test_call_above_put_itm(itm):
    assert itm.price("call") > itm.price("put")

def test_put_above_call_otm(otm):
    assert otm.price("put") > otm.price("call")

def test_call_intrinsic_at_expiry():
    calc = BSGreeks(S=110.0, K=100.0, T=0.0, r=0.05, sigma=0.20)
    assert calc.price("call") == pytest.approx(10.0, abs=0.01)

def test_put_intrinsic_at_expiry():
    calc = BSGreeks(S=90.0, K=100.0, T=0.0, r=0.05, sigma=0.20)
    assert calc.price("put") == pytest.approx(10.0, abs=0.01)

def test_known_bs_price():
    # Textbook: S=42, K=40, T=0.5, r=0.1, sigma=0.2 → call≈4.76
    calc = BSGreeks(S=42.0, K=40.0, T=0.5, r=0.10, sigma=0.20)
    assert calc.price("call") == pytest.approx(4.76, abs=0.05)


# ---- Put-call parity --------------------------------------------------------

def test_put_call_parity(atm):
    assert atm.put_call_parity_check() == pytest.approx(0.0, abs=1e-6)

def test_put_call_parity_itm(itm):
    assert itm.put_call_parity_check() == pytest.approx(0.0, abs=1e-6)


# ---- Delta ------------------------------------------------------------------

def test_call_delta_between_0_and_1(atm):
    d = atm.delta("call")
    assert 0.0 < d < 1.0

def test_put_delta_between_minus1_and_0(atm):
    d = atm.delta("put")
    assert -1.0 < d < 0.0

def test_call_put_delta_sum(atm):
    # call_delta - put_delta = 1 (for q=0)
    assert atm.delta("call") - atm.delta("put") == pytest.approx(1.0, abs=1e-4)

def test_deep_itm_call_delta_near_1(itm):
    assert itm.delta("call") > 0.80

def test_deep_otm_call_delta_near_0(otm):
    assert otm.delta("call") < 0.20


# ---- Gamma ------------------------------------------------------------------

def test_gamma_positive(atm):
    assert atm.gamma() > 0

def test_gamma_same_for_call_put(atm):
    # Gamma is identical for call and put
    assert atm.gamma() == pytest.approx(atm.gamma(), rel=1e-9)

def test_gamma_highest_atm():
    atm2  = BSGreeks(S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20)
    deep  = BSGreeks(S=140.0, K=100.0, T=1.0, r=0.05, sigma=0.20)
    assert atm2.gamma() > deep.gamma()


# ---- Theta ------------------------------------------------------------------

def test_call_theta_negative(atm):
    assert atm.theta("call") < 0

def test_put_theta_mostly_negative(atm):
    # Put theta is usually negative but can be positive deep ITM
    assert isinstance(atm.theta("put"), float)

def test_theta_in_daily_units(atm):
    # Daily theta should be much smaller than annual
    assert abs(atm.theta("call")) < abs(atm.price("call"))


# ---- Vega -------------------------------------------------------------------

def test_vega_positive(atm):
    assert atm.vega() > 0

def test_vega_same_call_put(atm):
    # Vega is the same for call and put (by BS formula)
    assert atm.vega() == pytest.approx(atm.vega(), rel=1e-9)

def test_vega_zero_at_expiry():
    calc = BSGreeks(S=100.0, K=100.0, T=0.0, r=0.05, sigma=0.20)
    assert calc.vega() == pytest.approx(0.0, abs=1e-9)


# ---- Rho --------------------------------------------------------------------

def test_call_rho_positive(atm):
    assert atm.rho("call") > 0

def test_put_rho_negative(atm):
    assert atm.rho("put") < 0

def test_rho_zero_at_expiry():
    calc = BSGreeks(S=100.0, K=100.0, T=0.0, r=0.05, sigma=0.20)
    assert calc.rho("call") == pytest.approx(0.0, abs=1e-9)


# ---- all_greeks snapshot ----------------------------------------------------

def test_all_greeks_returns_snapshot(atm):
    snap = atm.all_greeks("call")
    assert isinstance(snap, GreeksSnapshot)
    assert snap.kind == "call"

def test_all_greeks_consistent(atm):
    snap = atm.all_greeks("call")
    assert snap.price == pytest.approx(atm.price("call"), rel=1e-9)
    assert snap.delta == pytest.approx(atm.delta("call"), rel=1e-9)
    assert snap.gamma == pytest.approx(atm.gamma(), rel=1e-9)

def test_str_snapshot(atm):
    snap = atm.all_greeks("call")
    s = str(snap)
    assert "CALL" in s
    assert "price" in s


# ---- Input validation -------------------------------------------------------

def test_negative_S_raises():
    with pytest.raises(ValueError):
        BSGreeks(S=-1.0, K=100.0, T=1.0, r=0.05, sigma=0.20)

def test_negative_K_raises():
    with pytest.raises(ValueError):
        BSGreeks(S=100.0, K=-1.0, T=1.0, r=0.05, sigma=0.20)

def test_negative_T_raises():
    with pytest.raises(ValueError):
        BSGreeks(S=100.0, K=100.0, T=-0.1, r=0.05, sigma=0.20)

def test_negative_sigma_raises():
    with pytest.raises(ValueError):
        BSGreeks(S=100.0, K=100.0, T=1.0, r=0.05, sigma=-0.1)
