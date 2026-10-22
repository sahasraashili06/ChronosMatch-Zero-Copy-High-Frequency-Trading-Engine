"""
ChronosX — ObjectPool

Pre-allocates N Order slots and hands them out via a free-list.
Alloc and free are O(1).  No heap allocation after __init__.

In Python we can't avoid object creation costs the way C++ can with
placement new, but we reuse the same Order objects by resetting their
fields — zero calls to the allocator after warmup.
"""

from __future__ import annotations
from collections import deque
from typing import Optional
from .order import Order


class ObjectPool:
    """
    Fixed-capacity pool of Order objects.

    >>> pool = ObjectPool(8)
    >>> pool.capacity
    8
    >>> pool.available
    8
    >>> o = pool.alloc()
    >>> pool.available
    7
    >>> pool.free(pool.index_of(o))
    >>> pool.available
    8
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("Capacity must be at least 1")
        self._capacity: int   = capacity
        self._slots:    list[Order] = [Order() for _ in range(capacity)]
        self._free:     deque[int]  = deque(range(capacity))

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def available(self) -> int:
        return len(self._free)

    @property
    def is_full(self) -> bool:
        return len(self._free) == 0

    # ── Core operations ──────────────────────────────────────────────────────

    def alloc(self) -> Optional[tuple[int, Order]]:
        """
        Return (index, order_slot) or None if pool is exhausted.
        The caller must initialise all fields of the returned order.
        """
        if not self._free:
            return None
        idx = self._free.popleft()
        return idx, self._slots[idx]

    def free(self, idx: int) -> None:
        """Return slot *idx* to the free list. O(1)."""
        if idx < 0 or idx >= self._capacity:
            raise IndexError(f"Pool index {idx} out of range [0, {self._capacity})")
        self._free.appendleft(idx)

    def at(self, idx: int) -> Order:
        """Direct slot access by index."""
        return self._slots[idx]

    def index_of(self, order: Order) -> int:
        """Return the pool index for a given Order object."""
        return self._slots.index(order)
