
import multiprocessing as mp
import os
import tempfile
import time

from chronosx.mmap_ring_buffer import MmapRingBuffer

CAPACITY = 128
TOTAL_ORDERS = 1000


def producer(path, lock, count):
    buffer = MmapRingBuffer(path, CAPACITY, lock)

    try:
        for order_id in range(1, count + 1):
            side = 1 if order_id % 2 else -1
            price_ticks = 100_000 + order_id
            quantity = 10

            while not buffer.push(
                order_id, side, price_ticks, quantity
            ):
                time.sleep(0.0001)

        print(f"Producer wrote {count} orders", flush=True)
    finally:
        buffer.close()


def consumer(path, lock, count):
    buffer = MmapRingBuffer(path, CAPACITY, lock)

    try:
        for expected_id in range(1, count + 1):
            order = None

            while order is None:
                order = buffer.pop()
                if order is None:
                    time.sleep(0.0001)

            if order["order_id"] != expected_id:
                raise RuntimeError(
                    f"Expected order {expected_id}, got {order}"
                )

        print(f"Consumer verified {count} orders", flush=True)
    finally:
        buffer.close()


def main():
    ctx = mp.get_context("spawn")
    lock = ctx.Lock()

    fd, path = tempfile.mkstemp(
        prefix="chronosx_", suffix=".bin"
    )
    os.close(fd)

    initial = MmapRingBuffer(
        path, CAPACITY, lock, create=True
    )
    initial.close()

    producer_process = ctx.Process(
        target=producer,
        args=(path, lock, TOTAL_ORDERS),
    )
    consumer_process = ctx.Process(
        target=consumer,
        args=(path, lock, TOTAL_ORDERS),
    )

    start = time.perf_counter()

    try:
        consumer_process.start()
        producer_process.start()

        producer_process.join(timeout=30)
        consumer_process.join(timeout=30)

        for process in (producer_process, consumer_process):
            if process.is_alive():
                process.terminate()
                process.join()
                raise RuntimeError("IPC demo timed out")

            if process.exitcode != 0:
                raise RuntimeError(
                    f"Process failed: exit code {process.exitcode}"
                )

        elapsed = time.perf_counter() - start

        print(f"Total orders: {TOTAL_ORDERS}")
        print(f"Elapsed: {elapsed:.4f} seconds")
        print(f"Throughput: {TOTAL_ORDERS / elapsed:.0f} orders/sec")

    finally:
        for process in (producer_process, consumer_process):
            if process.is_alive():
                process.terminate()
                process.join()

        if os.path.exists(path):
            os.unlink(path)


if __name__ == "__main__":
    mp.freeze_support()
    main()
