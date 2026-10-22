"""
ChronosX — Zero-Copy HFT Matching Engine (Python)

Core domain types: prices, quantities, enums, and event dataclasses.
Prices are integer ticks (4 decimal places) — no floating point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

# ── Price multiplier ────────────────────────────────────────────────────────
# $1.2345 == 12_345 ticks.  All prices are int, never float.
PRICE_MULT: int = 10_000

INVALID_ORDER_ID: int = 0
INVALID_PRICE: int = -(2 ** 63)       # Sentinel — smallest int64 equivalent


# ── Enumerations ────────────────────────────────────────────────────────────

class Side(IntEnum):
    Buy  = 0
    Sell = 1


class OrderType(IntEnum):
    Limit  = 0
    Market = 1


class OrderStatus(IntEnum):
    New             = 0
    PartiallyFilled = 1
    Filled          = 2
    Cancelled       = 3
    Rejected        = 4


class RiskResult(IntEnum):
    Approved         = 0
    RejectedQty      = 1
    RejectedNotional = 2
    RejectedUnknown  = 3


# ── Event dataclasses ────────────────────────────────────────────────────────

@dataclass
class TradeEvent:
    """Emitted whenever two orders cross."""
    aggressor_id: int = INVALID_ORDER_ID
    resting_id:   int = INVALID_ORDER_ID
    price:        int = INVALID_PRICE
    qty:          int = 0


@dataclass
class CancelEvent:
    """Emitted when an order is cancelled (client or IOC residual)."""
    order_id:      int = INVALID_ORDER_ID
    remaining_qty: int = 0


@dataclass
class RejectEvent:
    """Emitted when an order is rejected by validation or risk."""
    order_id: int        = INVALID_ORDER_ID
    reason:   RiskResult = RiskResult.RejectedUnknown


@dataclass
class MatchResult:
    """Full outcome of a submit or cancel operation."""
    trades:       list[TradeEvent]    = field(default_factory=list)
    cancel_event: Optional[CancelEvent] = None
    reject_event: Optional[RejectEvent] = None
    final_status: OrderStatus           = OrderStatus.New
