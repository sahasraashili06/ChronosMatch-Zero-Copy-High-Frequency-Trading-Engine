"""
ChronosX — PriceLevel

An intrusive FIFO queue of Order pool-indices at a single price point.
Add: O(1) append to tail.
Remove: O(1) via doubly-linked list splice.
"""
from __future__ import annotations
from .order import Order, NULL_IDX
from .memory_pool import ObjectPool


class PriceLevel:
    """Doubly-linked FIFO list of order indices at one price."""

    def __init__(self) -> None:
        self._head: int = NULL_IDX   # oldest order (front of queue)
        self._tail: int = NULL_IDX   # newest order (back of queue)
        self._total_qty: int = 0
        self._count: int = 0

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def total_qty(self) -> int:
        return self._total_qty

    @property
    def order_count(self) -> int:
        return self._count

    @property
    def empty(self) -> bool:
        return self._head == NULL_IDX

    @property
    def front_idx(self) -> int:
        return self._head

    # ── Mutation ─────────────────────────────────────────────────────────────

    def add_order(self, idx: int, pool: ObjectPool) -> None:
        """Append order *idx* to the tail of the FIFO queue."""
        order = pool.at(idx)
        order.prev_idx = self._tail
        order.next_idx = NULL_IDX

        if self._tail != NULL_IDX:
            pool.at(self._tail).next_idx = idx
        else:
            self._head = idx          # list was empty

        self._tail = idx
        self._total_qty += order.remaining_qty
        self._count += 1

    def remove_order(self, idx: int, pool: ObjectPool) -> None:
        """Remove order *idx* from anywhere in the list.  O(1)."""
        order = pool.at(idx)
        prev = order.prev_idx
        nxt  = order.next_idx

        if prev != NULL_IDX:
            pool.at(prev).next_idx = nxt
        else:
            self._head = nxt          # removed the head

        if nxt != NULL_IDX:
            pool.at(nxt).prev_idx = prev
        else:
            self._tail = prev         # removed the tail

        self._total_qty -= order.remaining_qty
        self._count -= 1

        order.prev_idx = NULL_IDX
        order.next_idx = NULL_IDX

    def reduce_front_qty(self, delta: int) -> None:
        """Reduce total_qty when the front order is partially filled."""
        self._total_qty -= delta
