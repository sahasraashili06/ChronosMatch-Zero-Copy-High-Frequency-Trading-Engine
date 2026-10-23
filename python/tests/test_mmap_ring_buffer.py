
import multiprocessing
import pytest

from chronosx.mmap_ring_buffer import MmapRingBuffer


def test_push_and_pop(tmp_path):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()

    buffer = MmapRingBuffer(path, 4, lock, create=True)

    try:
        assert buffer.push(101, 1, 100500, 10) is True

        assert buffer.pop() == {
            "order_id": 101,
            "side": 1,
            "price_ticks": 100500,
            "quantity": 10,
        }

        assert buffer.pop() is None
    finally:
        buffer.close()


def test_full_buffer(tmp_path):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()

    buffer = MmapRingBuffer(path, 2, lock, create=True)

    try:
        assert buffer.push(1, 1, 10000, 5)
        assert buffer.push(2, -1, 10000, 5)
        assert not buffer.push(3, 1, 10000, 5)
    finally:
        buffer.close()


def test_invalid_side(tmp_path):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()

    buffer = MmapRingBuffer(path, 4, lock, create=True)

    try:
        with pytest.raises(ValueError):
            buffer.push(1, 0, 10000, 5)
    finally:
        buffer.close()
