
import multiprocessing as mp
import os
import tempfile
import time

from chronosx.mmap_ring_buffer import MmapRingBuffer


def producer(path, lock, count):
    buffer = MmapRingBuffer(path, 16, lock)

    try:
        for order_id in range(1, count + 1):
            while not buffer.push(
                order_id, 1, 100_000 + order_id, 10
            ):
                time.sleep(0.0001)
    finally:
        buffer.close()


def consumer(path, lock, count, results):
    buffer = MmapRingBuffer(path, 16, lock)

    try:
        received = []

        while len(received) < count:
            order = buffer.pop()

            if order is None:
                time.sleep(0.0001)
                continue

            received.append(order["order_id"])

        results.put(received)
    finally:
        buffer.close()


def test_cross_process_transfer():
    ctx = mp.get_context("spawn")
    lock = ctx.Lock()
    results = ctx.Queue()
    count = 100

    fd, path = tempfile.mkstemp(suffix=".bin")
    os.close(fd)

    initial = MmapRingBuffer(path, 16, lock, create=True)
    initial.close()

    producer_process = ctx.Process(
        target=producer,
        args=(path, lock, count),
    )
    consumer_process = ctx.Process(
        target=consumer,
        args=(path, lock, count, results),
    )

    try:
        consumer_process.start()
        producer_process.start()

        producer_process.join(timeout=15)
        consumer_process.join(timeout=15)

        assert not producer_process.is_alive(), "Producer timed out"
        assert not consumer_process.is_alive(), "Consumer timed out"
        assert producer_process.exitcode == 0
        assert consumer_process.exitcode == 0

        received = results.get(timeout=2)
        assert received == list(range(1, count + 1))

    finally:
        for process in (producer_process, consumer_process):
            if process.is_alive():
                process.terminate()
                process.join()

        results.close()

        if os.path.exists(path):
            os.unlink(path)


if __name__ == "__main__":
    mp.freeze_support()
