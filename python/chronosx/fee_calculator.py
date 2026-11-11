"""
ChronosX -- Exchange Fee Calculator

Computes maker/taker fees and net P&L after fees for every fill.
Supports tiered fee schedules (volume-based discounts).

Key concepts:
  - Maker : order that rested in the book (passive) → lower fee
  - Taker : order that crossed the spread (aggressive) → higher fee
  - Rebate: some exchanges pay makers a negative fee (rebate)

Usage:
    fee_calc = FeeCalculator(maker_bps=2.0, taker_bps=5.0)

    result = fee_calc.compute(
        notional=100_000_00,   # fixed-point: $1000.00
        is_maker=False,
    )
    print(f"Fee: ${result.fee_usd:.4f}")
    print(f"Net notional: ${result.net_notional_usd:.4f}")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .types import PRICE_MULT

BPS = 10_000.0   # 1 basis point = 0.0001


@dataclass
class FeeResult:
    notional:     int    # fixed-point gross notional
    fee:          int    # fixed-point fee (always positive)
    is_maker:     bool
    bps_applied:  float  # basis points used

    @property
    def notional_usd(self)     -> float: return self.notional / PRICE_MULT
    @property
    def fee_usd(self)          -> float: return self.fee      / PRICE_MULT
    @property
    def net_notional_usd(self) -> float: return (self.notional - self.fee) / PRICE_MULT

    def __str__(self) -> str:
        side = "maker" if self.is_maker else "taker"
        return (
            f"Fee[{side}]  notional=${self.notional_usd:.4f}  "
            f"fee=${self.fee_usd:.4f} ({self.bps_applied:.1f}bps)  "
            f"net=${self.net_notional_usd:.4f}"
        )


@dataclass
class FeeTier:
    """Volume tier: applies when 30-day volume >= min_volume (USD)."""
    min_volume_usd: float
    maker_bps:      float
    taker_bps:      float


class FeeCalculator:
    """
    Computes exchange fees with optional tiered schedule.

    Args:
        maker_bps   : default maker fee in basis points (can be negative = rebate).
        taker_bps   : default taker fee in basis points.
        tiers       : optional list of FeeTier for volume discounts.
        volume_30d  : current 30-day traded volume in USD (for tier selection).
    """

    def __init__(
        self,
        maker_bps:  float = 2.0,
        taker_bps:  float = 5.0,
        tiers:      Optional[List[FeeTier]] = None,
        volume_30d: float = 0.0,
    ) -> None:
        self._maker_bps  = maker_bps
        self._taker_bps  = taker_bps
        self._tiers      = sorted(tiers or [], key=lambda t: t.min_volume_usd, reverse=True)
        self._volume_30d = volume_30d
        self._total_fees:    int = 0
        self._total_notional: int = 0
        self._fill_count:    int = 0

    # ── Core API ──────────────────────────────────────────────────────────────

    def compute(self, notional: int, is_maker: bool) -> FeeResult:
        """
        Compute fee for one fill.

        Args:
            notional : gross notional in fixed-point (price × qty).
            is_maker : True if the order rested in the book.
        """
        bps  = self._effective_bps(is_maker)
        fee  = int(notional * bps / BPS)

        self._total_fees     += fee
        self._total_notional += notional
        self._fill_count     += 1

        return FeeResult(notional=notional, fee=fee, is_maker=is_maker, bps_applied=bps)

    def compute_from_price_qty(
        self, price: int, qty: int, is_maker: bool
    ) -> FeeResult:
        """Convenience wrapper: compute from price × qty."""
        return self.compute(notional=price * qty, is_maker=is_maker)

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def total_fees_usd(self) -> float:
        return self._total_fees / PRICE_MULT

    @property
    def total_notional_usd(self) -> float:
        return self._total_notional / PRICE_MULT

    @property
    def fill_count(self) -> int:
        return self._fill_count

    @property
    def effective_maker_bps(self) -> float:
        return self._effective_bps(is_maker=True)

    @property
    def effective_taker_bps(self) -> float:
        return self._effective_bps(is_maker=False)

    def set_volume_30d(self, volume_usd: float) -> None:
        """Update 30-day volume to recalculate tier."""
        self._volume_30d = volume_usd

    def reset_stats(self) -> None:
        self._total_fees = self._total_notional = self._fill_count = 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _effective_bps(self, is_maker: bool) -> float:
        for tier in self._tiers:
            if self._volume_30d >= tier.min_volume_usd:
                return tier.maker_bps if is_maker else tier.taker_bps
        return self._maker_bps if is_maker else self._taker_bps
