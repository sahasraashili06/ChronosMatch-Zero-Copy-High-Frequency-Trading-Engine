"""
ChronosX -- Market Impact Estimator

Estimates the price impact of executing a large order using the
Almgren-Chriss linear temporary + permanent impact model.

Reference:
  Almgren & Chriss (2000) "Optimal Execution of Portfolio Transactions"

Impact components:
  - Temporary : immediate price move during slice execution (recovers)
  - Permanent : lasting shift in equilibrium price (does not recover)
  - Total cost: sum over all slices of (qty * temporary_impact)

Key parameters (all fixed-point unless noted):
  eta   (temporary)   -- sensitivity in price units per unit of vol-normalised rate
  gamma (permanent)   -- permanent impact coefficient
  sigma               -- daily volatility (float, e.g. 0.02 = 2%)
  adv                 -- average daily volume (integer shares)

Usage:
    est = MarketImpactEstimator(
        eta=0.1, gamma=0.05,
        sigma=0.02, adv=1_000_000,
    )
    result = est.estimate(qty=50_000, mid_price=100_000, num_slices=10)
    print(f"Total cost: ${result.total_cost_usd:.2f}")
    print(f"Avg slippage per share: ${result.avg_slippage_usd:.4f}")
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

from .types import PRICE_MULT


@dataclass
class SliceImpact:
    slice_num:        int
    qty:              int
    temp_impact:      int    # fixed-point, price move during slice
    perm_impact:      int    # fixed-point, permanent shift
    execution_price:  int    # fixed-point, estimated fill price

    @property
    def temp_impact_usd(self) -> float: return self.temp_impact / PRICE_MULT
    @property
    def perm_impact_usd(self) -> float: return self.perm_impact / PRICE_MULT
    @property
    def execution_price_usd(self) -> float: return self.execution_price / PRICE_MULT


@dataclass
class ImpactResult:
    qty:             int        # total order qty
    num_slices:      int
    mid_price:       int        # fixed-point entry mid
    slices:          List[SliceImpact]
    total_perm:      int        # fixed-point total permanent impact
    total_temp_cost: int        # fixed-point total temporary cost (qty * temp)

    @property
    def total_cost_usd(self) -> float:
        return self.total_temp_cost / PRICE_MULT

    @property
    def total_perm_usd(self) -> float:
        return self.total_perm / PRICE_MULT

    @property
    def avg_slippage_usd(self) -> float:
        return self.total_cost_usd / self.qty if self.qty else 0.0

    @property
    def impact_bps(self) -> float:
        """Total impact as basis points of mid-price notional."""
        notional = self.qty * self.mid_price
        if notional == 0:
            return 0.0
        return (self.total_temp_cost / notional) * 10_000.0

    def __str__(self) -> str:
        return (
            f"ImpactResult  qty={self.qty}  slices={self.num_slices}  "
            f"total_cost=${self.total_cost_usd:.4f}  "
            f"avg_slip=${self.avg_slippage_usd:.6f}  "
            f"impact={self.impact_bps:.2f}bps"
        )


class MarketImpactEstimator:
    """
    Linear Almgren-Chriss market impact model.

    Temporary impact of a slice:
        temp_impact = eta * sigma * sqrt(T/N) * (qty_slice / adv)^0.5

    Permanent impact over full order:
        perm_impact = gamma * (total_qty / adv)

    Args:
        eta   : temporary impact coefficient (dimensionless, ~0.1).
        gamma : permanent impact coefficient (dimensionless, ~0.05).
        sigma : daily return volatility (float, e.g. 0.02).
        adv   : average daily volume in shares.
        days  : total execution horizon in trading days.
    """

    def __init__(
        self,
        eta:   float = 0.1,
        gamma: float = 0.05,
        sigma: float = 0.02,
        adv:   int   = 1_000_000,
        days:  float = 1.0,
    ) -> None:
        if adv <= 0:
            raise ValueError("adv must be positive")
        if sigma < 0:
            raise ValueError("sigma must be non-negative")
        self._eta   = eta
        self._gamma = gamma
        self._sigma = sigma
        self._adv   = adv
        self._days  = days

    # ---- Core API -----------------------------------------------------------

    def estimate(
        self,
        qty:        int,
        mid_price:  int,
        num_slices: int = 10,
    ) -> ImpactResult:
        """
        Estimate market impact for a given order.

        Args:
            qty        : total order quantity (shares).
            mid_price  : current mid price in fixed-point.
            num_slices : number of execution slices.
        """
        if qty <= 0:
            raise ValueError("qty must be positive")
        if num_slices <= 0:
            raise ValueError("num_slices must be positive")

        slice_qty   = qty // num_slices
        remainder   = qty % num_slices
        interval    = self._days / num_slices   # fraction of a day per slice

        # Permanent impact: shift equilibrium price by gamma * participation rate
        perm_rate        = qty / self._adv
        perm_bps_float   = self._gamma * perm_rate        # fractional price shift
        total_perm_fixed = int(mid_price * perm_bps_float)

        slices: List[SliceImpact] = []
        total_temp_cost  = 0
        cumulative_perm  = 0

        for i in range(num_slices):
            sq = slice_qty + (1 if i < remainder else 0)

            # Temporary impact: proportional to sqrt(participation rate per interval)
            participation = sq / (self._adv * interval) if interval > 0 else 0.0
            temp_float    = self._eta * self._sigma * math.sqrt(interval) * math.sqrt(max(participation, 0.0))
            temp_fixed    = int(mid_price * temp_float)

            # Permanent impact accumulates across slices
            slice_perm    = total_perm_fixed // num_slices
            cumulative_perm += slice_perm

            exec_price = mid_price + temp_fixed + cumulative_perm

            slices.append(SliceImpact(
                slice_num       = i + 1,
                qty             = sq,
                temp_impact     = temp_fixed,
                perm_impact     = slice_perm,
                execution_price = exec_price,
            ))

            total_temp_cost += sq * temp_fixed

        return ImpactResult(
            qty             = qty,
            num_slices      = num_slices,
            mid_price       = mid_price,
            slices          = slices,
            total_perm      = total_perm_fixed,
            total_temp_cost = total_temp_cost,
        )

    def participation_rate(self, qty: int, duration_days: float) -> float:
        """Fraction of ADV this order represents."""
        return qty / (self._adv * duration_days) if duration_days > 0 else 0.0

    def breakeven_spread_bps(self, qty: int, mid_price: int) -> float:
        """Minimum spread needed for a round-trip to be profitable."""
        result = self.estimate(qty=qty, mid_price=mid_price)
        return result.impact_bps * 2
