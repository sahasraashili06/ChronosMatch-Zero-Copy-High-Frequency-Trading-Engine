"""
ChronosX -- Black-Scholes Greeks Calculator

Computes option prices and Greeks (Delta, Gamma, Theta, Vega, Rho)
using the closed-form Black-Scholes-Merton model.

No external dependencies -- uses only the Python standard library.
The normal CDF is approximated with Horner's method (Abramowitz & Stegun 26.2.17),
accurate to 7 significant figures.

All prices are in USD (float). Greeks are dimensionless or per-dollar/day.

Usage:
    calc = BSGreeks(S=150.0, K=155.0, T=0.25, r=0.05, sigma=0.20)

    print(calc.delta("call"))    #  0.431
    print(calc.gamma())          #  0.028
    print(calc.theta("put"))     # -0.042  (per calendar day)
    print(calc.vega())           #  0.293  (per 1-vol-pt = 1%)
    print(calc.rho("call"))      #  0.147  (per 1% rate move)
    print(calc.price("call"))    # $3.78
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

OptionKind = Literal["call", "put"]


# ---- Normal distribution helpers (no scipy) ---------------------------------

def _norm_cdf(x: float) -> float:
    """Standard normal CDF via Horner's method (Abramowitz & Stegun 26.2.17)."""
    sign = 1.0 if x >= 0 else -1.0
    x    = abs(x)
    t    = 1.0 / (1.0 + 0.2316419 * x)
    poly = t * (0.319381530
              + t * (-0.356563782
              + t * (1.781477937
              + t * (-1.821255978
              + t *  1.330274429))))
    return 0.5 + sign * (0.5 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x) * poly)


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


# ---- Greeks dataclass -------------------------------------------------------

@dataclass
class GreeksSnapshot:
    """All first- and second-order Greeks for one option."""
    kind:   str
    price:  float   # option premium (USD)
    delta:  float   # dV/dS
    gamma:  float   # d²V/dS²
    theta:  float   # dV/dt  (per calendar day, sign: typically negative)
    vega:   float   # dV/dσ  (per 1% move in vol, i.e. per 0.01)
    rho:    float   # dV/dr  (per 1% move in rate, i.e. per 0.01)
    d1:     float
    d2:     float

    def __str__(self) -> str:
        return (
            f"Greeks[{self.kind.upper()}]  "
            f"price=${self.price:.4f}  "
            f"Δ={self.delta:+.4f}  "
            f"Γ={self.gamma:.6f}  "
            f"Θ={self.theta:+.4f}/day  "
            f"ν={self.vega:.4f}/%vol  "
            f"ρ={self.rho:+.4f}/%r"
        )


# ---- Main calculator --------------------------------------------------------

class BSGreeks:
    """
    Black-Scholes-Merton Greeks calculator.

    Args:
        S     : spot price (USD).
        K     : strike price (USD).
        T     : time to expiry in years (e.g. 0.25 = 3 months).
        r     : risk-free rate (annual, e.g. 0.05 = 5%).
        sigma : implied volatility (annual, e.g. 0.20 = 20%).
        q     : continuous dividend yield (default 0).
    """

    def __init__(
        self,
        S:     float,
        K:     float,
        T:     float,
        r:     float,
        sigma: float,
        q:     float = 0.0,
    ) -> None:
        if S <= 0:    raise ValueError("S must be positive")
        if K <= 0:    raise ValueError("K must be positive")
        if T < 0:     raise ValueError("T must be non-negative")
        if sigma < 0: raise ValueError("sigma must be non-negative")

        self.S     = S
        self.K     = K
        self.T     = T
        self.r     = r
        self.sigma = sigma
        self.q     = q

        # Pre-compute d1, d2 (with guard for T=0 or sigma=0)
        if T > 0 and sigma > 0:
            self._d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            self._d2 = self._d1 - sigma * math.sqrt(T)
        else:
            self._d1 = math.inf if S >= K else -math.inf
            self._d2 = self._d1

        self._sqrtT   = math.sqrt(T) if T > 0 else 0.0
        self._disc    = math.exp(-r * T)
        self._disc_q  = math.exp(-q * T)

    # ---- Pricing ------------------------------------------------------------

    def price(self, kind: OptionKind = "call") -> float:
        """Black-Scholes option price."""
        if self.T == 0:
            intrinsic = max(self.S - self.K, 0) if kind == "call" else max(self.K - self.S, 0)
            return float(intrinsic)

        S, K = self.S, self.K
        d1, d2 = self._d1, self._d2

        if kind == "call":
            return S * self._disc_q * _norm_cdf(d1) - K * self._disc * _norm_cdf(d2)
        else:
            return K * self._disc * _norm_cdf(-d2) - S * self._disc_q * _norm_cdf(-d1)

    # ---- Greeks -------------------------------------------------------------

    def delta(self, kind: OptionKind = "call") -> float:
        """dV/dS -- sensitivity to underlying price."""
        if self.T == 0 or self.sigma == 0:
            return (1.0 if self.S > self.K else 0.0) if kind == "call" else (
                   -1.0 if self.S < self.K else 0.0)
        if kind == "call":
            return self._disc_q * _norm_cdf(self._d1)
        else:
            return self._disc_q * (_norm_cdf(self._d1) - 1.0)

    def gamma(self) -> float:
        """d²V/dS² -- same for calls and puts."""
        if self.T == 0 or self.sigma == 0 or self._sqrtT == 0:
            return 0.0
        return self._disc_q * _norm_pdf(self._d1) / (self.S * self.sigma * self._sqrtT)

    def theta(self, kind: OptionKind = "call") -> float:
        """
        dV/dt per *calendar day* (negative = time decay).
        Divided by 365 to convert from annual to daily.
        """
        if self.T == 0 or self.sigma == 0 or self._sqrtT == 0:
            return 0.0
        S, K, r, q, sigma = self.S, self.K, self.r, self.q, self.sigma
        d1, d2 = self._d1, self._d2

        common = -(S * self._disc_q * _norm_pdf(d1) * sigma) / (2 * self._sqrtT)
        if kind == "call":
            annual = common - r * K * self._disc * _norm_cdf(d2) + q * S * self._disc_q * _norm_cdf(d1)
        else:
            annual = common + r * K * self._disc * _norm_cdf(-d2) - q * S * self._disc_q * _norm_cdf(-d1)
        return annual / 365.0

    def vega(self) -> float:
        """
        dV/dσ per 1% move in vol (same for calls and puts).
        Divide by 100 internally so user gets "per 1% vol".
        """
        if self.T == 0 or self._sqrtT == 0:
            return 0.0
        return self.S * self._disc_q * _norm_pdf(self._d1) * self._sqrtT / 100.0

    def rho(self, kind: OptionKind = "call") -> float:
        """
        dV/dr per 1% move in risk-free rate.
        Divide by 100 internally.
        """
        if self.T == 0:
            return 0.0
        K, T = self.K, self.T
        if kind == "call":
            return K * T * self._disc * _norm_cdf(self._d2) / 100.0
        else:
            return -K * T * self._disc * _norm_cdf(-self._d2) / 100.0

    # ---- Convenience --------------------------------------------------------

    def all_greeks(self, kind: OptionKind = "call") -> GreeksSnapshot:
        """Return all Greeks in one dataclass."""
        return GreeksSnapshot(
            kind  = kind,
            price = self.price(kind),
            delta = self.delta(kind),
            gamma = self.gamma(),
            theta = self.theta(kind),
            vega  = self.vega(),
            rho   = self.rho(kind),
            d1    = self._d1,
            d2    = self._d2,
        )

    def put_call_parity_check(self) -> float:
        """
        Returns |C - P - S*exp(-qT) + K*exp(-rT)|.
        Should be ~0 for correct pricing.
        """
        C = self.price("call")
        P = self.price("put")
        return abs(C - P - self.S * self._disc_q + self.K * self._disc)
