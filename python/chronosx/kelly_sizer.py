"""
ChronosX -- Kelly Criterion Position Sizer

Computes the optimal fraction of capital to risk on each trade
using the Kelly formula. Prevents over-sizing (ruin) and
under-sizing (missed returns).

    Kelly % = W - (1 - W) / R

    where:
        W = win rate  (fraction of trades that are profitable)
        R = win/loss ratio  (avg win size / avg loss size)

Variants:
  - Full Kelly : aggressive, maximises log-wealth growth
  - Half Kelly : conservative, halves the Kelly fraction
  - Fractional : custom scaling factor

Usage:
    ks = KellySizer(capital=100_000_00, fraction=0.5)  # half-kelly, $100k
    ks.record_trade(pnl=500)    # winning trade
    ks.record_trade(pnl=-200)   # losing trade

    size = ks.position_size(price=100_000)  # shares to buy
    print(f"Trade {size} shares")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .types import PRICE_MULT


@dataclass
class KellyStats:
    win_count:  int
    loss_count: int
    avg_win:    float   # USD
    avg_loss:   float   # USD (positive number)
    kelly_pct:  float   # raw Kelly fraction
    used_pct:   float   # after applying fraction multiplier

    @property
    def total_trades(self) -> int:
        return self.win_count + self.loss_count

    @property
    def win_rate(self) -> float:
        return self.win_count / self.total_trades if self.total_trades else 0.0

    @property
    def win_loss_ratio(self) -> float:
        return self.avg_win / self.avg_loss if self.avg_loss else 0.0

    def __str__(self) -> str:
        return (
            f"Kelly: W={self.win_rate:.1%}  R={self.win_loss_ratio:.2f}  "
            f"Kelly%={self.kelly_pct:.1%}  Used%={self.used_pct:.1%}  "
            f"trades={self.total_trades}"
        )


class KellySizer:
    """
    Tracks trade outcomes and recommends position sizes via Kelly criterion.

    Args:
        capital:  Total trading capital in USD (float).
        fraction: Scaling factor applied to raw Kelly (0.5 = half-Kelly).
        min_trades: Minimum trades needed before giving a size recommendation.
    """

    def __init__(
        self,
        capital:    float = 100_000.0,
        fraction:   float = 0.5,
        min_trades: int   = 10,
    ) -> None:
        if not (0 < fraction <= 1.0):
            raise ValueError("fraction must be in (0, 1]")
        if capital <= 0:
            raise ValueError("capital must be positive")

        self._capital    = capital
        self._fraction   = fraction
        self._min_trades = min_trades
        self._wins:      List[float] = []
        self._losses:    List[float] = []

    # ── Feed ──────────────────────────────────────────────────────────────────

    def record_trade(self, pnl: float) -> None:
        """Record a completed trade P&L in USD. Positive = win, negative = loss."""
        if pnl > 0:
            self._wins.append(pnl)
        elif pnl < 0:
            self._losses.append(abs(pnl))

    def record_trade_fixed(self, pnl_fixed: int) -> None:
        """Record P&L as a fixed-point integer (will be converted to USD)."""
        self.record_trade(pnl_fixed / PRICE_MULT)

    # ── Position sizing ───────────────────────────────────────────────────────

    def kelly_fraction(self) -> Optional[float]:
        """
        Returns the raw Kelly fraction, or None if insufficient data.
        Clamped to [0, 1].
        """
        if (len(self._wins) + len(self._losses)) < self._min_trades:
            return None
        if not self._wins or not self._losses:
            return None

        w = len(self._wins) / (len(self._wins) + len(self._losses))
        r = (sum(self._wins) / len(self._wins)) / (sum(self._losses) / len(self._losses))

        kelly = w - (1 - w) / r
        return max(0.0, min(1.0, kelly))

    def recommended_fraction(self) -> Optional[float]:
        """Kelly fraction × scaling factor."""
        k = self.kelly_fraction()
        return k * self._fraction if k is not None else None

    def position_size(self, price_fixed: int) -> Optional[int]:
        """
        Recommended shares/contracts to trade at *price_fixed*.
        Returns None if not enough data yet.
        """
        frac = self.recommended_fraction()
        if frac is None or price_fixed <= 0:
            return None
        price_usd  = price_fixed / PRICE_MULT
        dollar_risk = self._capital * frac
        shares      = int(dollar_risk / price_usd)
        return max(0, shares)

    def position_size_usd(self) -> Optional[float]:
        """Dollar amount to allocate (capital × used fraction)."""
        frac = self.recommended_fraction()
        return self._capital * frac if frac is not None else None

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def capital(self) -> float:
        return self._capital

    def update_capital(self, new_capital: float) -> None:
        self._capital = new_capital

    @property
    def trade_count(self) -> int:
        return len(self._wins) + len(self._losses)

    @property
    def win_count(self) -> int:
        return len(self._wins)

    @property
    def loss_count(self) -> int:
        return len(self._losses)

    def stats(self) -> Optional[KellyStats]:
        if self.trade_count < self._min_trades:
            return None
        k = self.kelly_fraction()
        if k is None:
            return None
        avg_win  = sum(self._wins)  / len(self._wins)  if self._wins  else 0.0
        avg_loss = sum(self._losses)/ len(self._losses) if self._losses else 0.0
        return KellyStats(
            win_count  = len(self._wins),
            loss_count = len(self._losses),
            avg_win    = avg_win,
            avg_loss   = avg_loss,
            kelly_pct  = k,
            used_pct   = k * self._fraction,
        )

    def reset(self) -> None:
        self._wins.clear()
        self._losses.clear()
