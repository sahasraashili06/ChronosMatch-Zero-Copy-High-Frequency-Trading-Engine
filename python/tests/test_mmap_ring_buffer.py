
import multiprocessing
import pytest

from chronosx.mmap_ring_buffer import HEADER, MmapRingBuffer


def test_corrupted_header_head_exceeds_tail(tmp_path):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()

    buffer = MmapRingBuffer(path, 4, lock, create=True)
    buffer.close()

    with open(path, "r+b") as file:
        file.write(HEADER.pack(5, 3, 4))

    with pytest.raises(ValueError, match="head exceeds tail"):
        MmapRingBuffer(path, 4, lock)


def test_corrupted_header_occupancy_exceeds_capacity(tmp_path):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()

    buffer = MmapRingBuffer(path, 4, lock, create=True)
    buffer.close()

    with open(path, "r+b") as file:
        file.write(HEADER.pack(0, 5, 4))

    with pytest.raises(ValueError, match="occupancy exceeds capacity"):
        MmapRingBuffer(path, 4, lock)


def test_empty_buffer(tmp_path):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()
    buffer = MmapRingBuffer(path, 4, lock, create=True)

    try:
        assert buffer.pop() is None
    finally:
        buffer.close()


def test_wraparound(tmp_path):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()
    buffer = MmapRingBuffer(path, 2, lock, create=True)

    try:
        assert buffer.push(1, 1, 10000, 5)
        assert buffer.push(2, -1, 11000, 10)

        assert buffer.pop()["order_id"] == 1
        assert buffer.pop()["order_id"] == 2

        assert buffer.push(3, 1, 12000, 15)
        assert buffer.push(4, -1, 13000, 20)

        assert buffer.pop()["order_id"] == 3
        assert buffer.pop()["order_id"] == 4
        assert buffer.pop() is None
    finally:
        buffer.close()


def test_fifo_ordering(tmp_path):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()
    buffer = MmapRingBuffer(path, 4, lock, create=True)

    try:
        for order_id in range(1, 5):
            assert buffer.push(order_id, 1, 10000, 5)

        received = [
            buffer.pop()["order_id"]
            for _ in range(4)
        ]

        assert received == [1, 2, 3, 4]
    finally:
        buffer.close()


def test_invalid_capacity():
    with pytest.raises(ValueError):
        MmapRingBuffer(
            "unused.bin",
            1,
            multiprocessing.Lock()
        )


@pytest.mark.parametrize("order_id", [-1, 2**64])
def test_invalid_order_id(tmp_path, order_id):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()
    buffer = MmapRingBuffer(path, 4, lock, create=True)

    try:
        with pytest.raises(ValueError):
            buffer.push(order_id, 1, 10000, 5)
    finally:
        buffer.close()


@pytest.mark.parametrize("price_ticks", [-(2**63)-1, 2**63])
def test_invalid_price(tmp_path, price_ticks):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()
    buffer = MmapRingBuffer(path, 4, lock, create=True)

    try:
        with pytest.raises(ValueError):
            buffer.push(1, 1, price_ticks, 5)
    finally:
        buffer.close()


@pytest.mark.parametrize("quantity", [-1, 2**64])
def test_invalid_quantity(tmp_path, quantity):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()
    buffer = MmapRingBuffer(path, 4, lock, create=True)

    try:
        with pytest.raises(ValueError):
            buffer.push(1, 1, 10000, quantity)
    finally:
        buffer.close()


def test_capacity_mismatch(tmp_path):
    path = str(tmp_path / "orders.bin")
    lock = multiprocessing.Lock()

    buffer = MmapRingBuffer(path, 4, lock, create=True)
    buffer.close()

    with pytest.raises(ValueError, match="file size"):
        MmapRingBuffer(path, 8, lock)
