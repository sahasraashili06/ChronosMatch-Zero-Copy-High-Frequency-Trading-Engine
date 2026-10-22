
"""Fixed-size shared-memory ring buffer for ChronosMatch.

Records are written directly into a memory-mapped file.
A multiprocessing lock coordinates one producer and one consumer.
No JSON or Pickle serialization is used for order records.
"""

import mmap
import os
import struct
from multiprocessing.synchronize import Lock as ProcessLock
from typing import Optional


# Header: read index, write index, capacity
HEADER = struct.Struct("<QQQ")

# Order: order_id, side, padding, price_ticks, quantity
# side: 1 = BUY, -1 = SELL
ORDER = struct.Struct("<Qb7xqQ")


class MmapRingBuffer:
    def __init__(
        self,
        path: str,
        capacity: int,
        lock: ProcessLock,
        create: bool = False,
    ) -> None:
        if capacity < 2:
            raise ValueError("Capacity must be at least 2")

        self.path = path
        self.lock = lock
        self.capacity = capacity
        self.size = HEADER.size + capacity * ORDER.size

        if create:
            with open(path, "w+b") as f:
                f.truncate(self.size)

        self._file = open(path, "r+b")

        if os.path.getsize(path) != self.size:
            self._file.close()
            raise ValueError(
                "Shared file size does not match the requested capacity"
            )

        self._map = mmap.mmap(self._file.fileno(), self.size)

        if create:
            HEADER.pack_into(self._map, 0, 0, 0, capacity)
        else:
            _, _, stored_capacity = HEADER.unpack_from(self._map, 0)
            if stored_capacity != capacity:
                self.close()
                raise ValueError("Ring buffer capacity mismatch")

    def push(
        self,
        order_id: int,
        side: int,
        price_ticks: int,
        quantity: int,
    ) -> bool:
        if side not in (-1, 1):
            raise ValueError("side must be 1 (BUY) or -1 (SELL)")
        if not 0 <= order_id < 2**64:
            raise ValueError("order_id must fit in uint64")
        if not -(2**63) <= price_ticks < 2**63:
            raise ValueError("price_ticks must fit in int64")
        if not 0 <= quantity < 2**64:
            raise ValueError("quantity must fit in uint64")

        with self.lock:
            head, tail, capacity = HEADER.unpack_from(self._map, 0)

            if tail - head >= capacity:
                return False

            slot = tail % capacity
            offset = HEADER.size + slot * ORDER.size

            ORDER.pack_into(
                self._map,
                offset,
                order_id,
                side,
                price_ticks,
                quantity,
            )

            HEADER.pack_into(
                self._map, 0, head, tail + 1, capacity
            )
            return True

    def pop(self) -> Optional[dict]:
        with self.lock:
            head, tail, capacity = HEADER.unpack_from(self._map, 0)

            if head == tail:
                return None

            slot = head % capacity
            offset = HEADER.size + slot * ORDER.size

            order_id, side, price_ticks, quantity = (
                ORDER.unpack_from(self._map, offset)
            )

            HEADER.pack_into(
                self._map, 0, head + 1, tail, capacity
            )

            return {
                "order_id": order_id,
                "side": side,
                "price_ticks": price_ticks,
                "quantity": quantity,
            }

    def close(self) -> None:
        if getattr(self, "_map", None) is not None:
            self._map.close()
            self._map = None

        if getattr(self, "_file", None) is not None:
            self._file.close()
            self._file = None
