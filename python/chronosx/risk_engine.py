"""
ChronosX — RiskEngine

Pre-trade risk checks applied to every incoming order before it touches
the matching engine. Checks quantity and notional value limits.
"""
from __future__ import annotations
from dataclasses import dataclass
from .types import Side, RiskResult

MAX_NOTIONAL_DEFAULT: int = 10_000_000 * 10_000   # $10,000,000 in ticks
MAX_QTY_DEFAULT:      int = 10_000


@dataclass
class RiskLimits:
    max_order_qty:      int = MAX_QTY_DEFAULT
    max_order_notional: int = MAX_NOTIONAL_DEFAULT


class RiskEngine:
    """
    Stateless pre-trade risk gate.

    >>> engine = RiskEngine()
    >>> engine.check_order(Side.Buy, 100_000, 10)
    <RiskResult.Approved: 0>
    >>> engine.check_order(Side.Buy, 100_000, 99_999)
    <RiskResult.RejectedQty: 1>
    """

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self._limits = limits or RiskLimits()

    @property
    def limits(self) -> RiskLimits:
        return self._limits

    def check_order(self, side: Side, price: int, qty: int) -> RiskResult:
        # ── Check 1: Quantity limit ──────────────────────────────────────────
        if qty > self._limits.max_order_qty:
            return RiskResult.RejectedQty

        # ── Check 2: Notional limit (price × qty) ───────────────────────────
        # Python ints are arbitrary precision — no overflow risk.
        if price > 0:
            notional = price * qty
            if notional > self._limits.max_order_notional:
                return RiskResult.RejectedNotional

        return RiskResult.Approved
