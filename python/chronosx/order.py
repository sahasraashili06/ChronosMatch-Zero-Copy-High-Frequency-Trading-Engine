"""
ChronosX — Order dataclass.

In the C++ version each Order occupies exactly one 64-byte cache line.
In Python we can't control memory layout the same way, but we keep the
same field set and semantics so the port is a faithful translation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from .types import (
    INVALID_ORDER_ID, INVALID_PRICE,
    Side, OrderType, OrderStatus
)

NULL_IDX: int = -1   # Sentinel pool index (equivalent to C++ kNullIdx / UINT32_MAX)


@dataclass
class Order:
    """A single order node — the fundamental unit of the matching engine."""
    order_id:      int         = INVALID_ORDER_ID
    price:         int         = INVALID_PRICE
    initial_qty:   int         = 0
    remaining_qty: int         = 0
    seq_num:       int         = 0
    prev_idx:      int         = NULL_IDX
    next_idx:      int         = NULL_IDX
    type:          OrderType   = OrderType.Limit
    side:          Side        = Side.Buy
    # Unallocated pool slots default to Rejected so is_active() == False
    status:        OrderStatus = OrderStatus.Rejected

    # ── Helpers ──────────────────────────────────────────────────────────────

    def is_active(self) -> bool:
        return self.status in (OrderStatus.New, OrderStatus.PartiallyFilled)

    def is_fully_filled(self) -> bool:
        return self.remaining_qty == 0

    def filled_qty(self) -> int:
        return self.initial_qty - self.remaining_qty

    def __repr__(self) -> str:
        side_str = "BUY" if self.side == Side.Buy else "SELL"
        return (
            f"Order(id={self.order_id} {side_str} "
            f"qty={self.remaining_qty}/{self.initial_qty} "
            f"@{self.price} {self.status.name})"
        )
