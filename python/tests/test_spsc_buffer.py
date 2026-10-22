"""Tests for SpscRingBuffer"""
import threading
import pytest
from chronosx.spsc_ring_buffer import SpscRingBuffer


def test_initially_empty():
    buf: SpscRingBuffer[int] = SpscRingBuffer(8)
    assert buf.empty()
    assert buf.size() == 0


def test_push_and_pop():
    buf: SpscRingBuffer[int] = SpscRingBuffer(8)
    assert buf.push(42)
    assert buf.pop() == 42


def test_fifo_ordering():
    buf: SpscRingBuffer[int] = SpscRingBuffer(8)
    for i in range(5):
        buf.push(i)
    for i in range(5):
        assert buf.pop() == i


def test_fills_to_capacity():
    buf: SpscRingBuffer[int] = SpscRingBuffer(4)
    assert buf.push(1)
    assert buf.push(2)
    assert buf.push(3)
    assert buf.push(4)
    assert not buf.push(5)   # full


def test_pop_from_empty_returns_none():
    buf: SpscRingBuffer[int] = SpscRingBuffer(4)
    assert buf.pop() is None


def test_wrap_around():
    buf: SpscRingBuffer[int] = SpscRingBuffer(4)
    for i in range(4): buf.push(i)
    for _ in range(2): buf.pop()
    buf.push(10); buf.push(11)
    assert buf.pop() == 2
    assert buf.pop() == 3
    assert buf.pop() == 10
    assert buf.pop() == 11


def test_capacity_must_be_power_of_two():
    with pytest.raises(ValueError):
        SpscRingBuffer(3)
    with pytest.raises(ValueError):
        SpscRingBuffer(0)


def test_producer_consumer_thread():
    buf: SpscRingBuffer[int] = SpscRingBuffer(256)
    N = 1000
    received = []
    done = threading.Event()

    def producer():
        for i in range(N):
            while not buf.push(i):
                pass
        done.set()

    t = threading.Thread(target=producer)
    t.start()
    while not done.is_set() or not buf.empty():
        v = buf.pop()
        if v is not None:
            received.append(v)
    while True:
        v = buf.pop()
        if v is None: break
        received.append(v)
    t.join()

    assert len(received) == N
    assert received == list(range(N))
