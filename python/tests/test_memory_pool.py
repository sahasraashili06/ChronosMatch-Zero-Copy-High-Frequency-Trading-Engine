"""Tests for ObjectPool"""
import pytest
from chronosx.memory_pool import ObjectPool


def test_initial_capacity():
    pool = ObjectPool(8)
    assert pool.capacity  == 8
    assert pool.available == 8
    assert not pool.is_full


def test_single_alloc_and_free():
    pool = ObjectPool(4)
    result = pool.alloc()
    assert result is not None
    idx, order = result
    assert pool.available == 3
    pool.free(idx)
    assert pool.available == 4


def test_alloc_until_full():
    pool = ObjectPool(4)
    slots = [pool.alloc() for _ in range(4)]
    assert all(s is not None for s in slots)
    assert pool.is_full
    assert pool.alloc() is None


def test_free_list_reuse():
    pool = ObjectPool(4)
    r1 = pool.alloc(); assert r1 is not None
    idx1, _ = r1
    pool.free(idx1)
    r2 = pool.alloc(); assert r2 is not None
    idx2, _ = r2
    assert idx2 == idx1   # LIFO reuse


def test_at_returns_correct_slot():
    pool = ObjectPool(4)
    result = pool.alloc()
    assert result is not None
    idx, order = result
    assert pool.at(idx) is order


def test_out_of_range_free_raises():
    pool = ObjectPool(4)
    with pytest.raises(IndexError):
        pool.free(99)


def test_large_capacity():
    pool = ObjectPool(1024)
    assert pool.capacity == 1024
    assert pool.available == 1024
