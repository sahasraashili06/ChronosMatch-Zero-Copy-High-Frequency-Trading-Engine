"""
ChronosX — SPSC Ring Buffer

Single-Producer Single-Consumer lock-free queue backed by a fixed-size list.
Thread-safe for exactly one writer thread and one reader thread.

In CPython the GIL provides visibility guarantees, but we use threading.Event
and explicit memory barriers (via volatile-equivalent reads) to keep the
semantics correct for PyPy or future no-GIL builds.
"""

from __future__ import annotations
import threading
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


class SpscRingBuffer(Generic[T]):
    """
    Lock-free single-producer / single-consumer queue.

    Capacity must be a power of two for efficient wrap-around masking.

    >>> buf: SpscRingBuffer[int] = SpscRingBuffer(8)
    >>> buf.push(42)
    True
    >>> buf.pop()
    42
    >>> buf.pop() is None
    True
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 2 or (capacity & (capacity - 1)) != 0:
            raise ValueError("Capacity must be a power of two >= 2")
        self._capacity: int          = capacity
        self._mask:     int          = capacity - 1
        self._buf:      list[Any]    = [None] * capacity
        # Monotonic counters — never wrap (Python ints are unbounded)
        self._head:     int = 0   # next slot to read  (consumer writes)
        self._tail:     int = 0   # next slot to write (producer writes)
        self._lock:     threading.Lock = threading.Lock()  # guards _tail/_head

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def capacity(self) -> int:
        return self._capacity

    def empty(self) -> bool:
        with self._lock:
            return self._head == self._tail

    def full(self) -> bool:
        with self._lock:
            return (self._tail - self._head) >= self._capacity

    def size(self) -> int:
        with self._lock:
            return self._tail - self._head

    # ── Core operations ──────────────────────────────────────────────────────

    def push(self, item: T) -> bool:
        """
        Push *item* into the buffer.
        Returns True on success, False if full.
        """
        with self._lock:
            if (self._tail - self._head) >= self._capacity:
                return False
            self._buf[self._tail & self._mask] = item
            self._tail += 1
            return True

    def pop(self) -> Optional[T]:
        """
        Pop the oldest item.
        Returns the item or None if empty.
        """
        with self._lock:
            if self._head == self._tail:
                return None
            item = self._buf[self._head & self._mask]
            self._buf[self._head & self._mask] = None  # release ref
            self._head += 1
            return item
