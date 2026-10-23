/**
 * @file spsc_ring_buffer.hpp
 * @brief Lock-free Single-Producer Single-Consumer (SPSC) ring buffer.
 *
 * ## Design Rationale
 * A mutex-based queue introduces kernel transitions and unbounded latency.
 * An SPSC ring buffer communicates between exactly one producer thread and
 * one consumer thread using only atomic loads/stores with acquire-release
 * memory ordering — no locks, no system calls.
 *
 * ## Memory Ordering
 *   push():
 *     1. Reads head_ with memory_order_acquire (synchronises with consumer's
 *        store to head_ in pop()).
 *     2. Writes the element into buffer_ (ordinary store — producer owns slot).
 *     3. Stores to tail_ with memory_order_release so the consumer sees the
 *        element before the updated tail_.
 *
 *   pop():
 *     1. Reads tail_ with memory_order_acquire (synchronises with producer's
 *        release store to tail_ in push()).
 *     2. Reads the element from buffer_ (ordinary load — consumer now owns slot).
 *     3. Stores to head_ with memory_order_release so the producer sees the
 *        freed slot before the updated head_.
 *
 * ## False-Sharing Mitigation
 * head_ and tail_ are placed on separate 64-byte cache lines (alignas(64)).
 * Without this, writes by one thread would invalidate the cache line
 * containing the other thread's atomic variable, causing expensive cache
 * coherency traffic (false sharing).
 *
 * ## Capacity Contract
 *   - Capacity MUST be a power of two (enforced by static_assert).
 *   - Slot indexing: counter & (Capacity-1)  — a single AND instruction.
 *   - Counters grow monotonically (simple +1) and rely on natural size_t
 *     wrap-around after ~1.8×10^19 operations — effectively never.
 *   - Full check: (tail - head) >= Capacity  (distance-based, not equality).
 *   - Actual usable slots = Capacity (unlike the "one slot empty" variant).
 *   - Overflow: push() returns false; caller is responsible for retry/drop.
 *   - Underflow: pop() returns false; caller should spin or yield.
 *
 * ## Thread Safety
 *   - Exactly ONE producer thread and ONE consumer thread.
 *   - Do NOT call push() from multiple threads or pop() from multiple threads.
 */

#pragma once

#include <atomic>
#include <cassert>
#include <cstddef>
#include <type_traits>

namespace chronosx {
    #ifdef _MSC_VER
#pragma warning(push)
#pragma warning(disable : 4324)
#endif

template <typename T, std::size_t Capacity>
class SpscRingBuffer {
    static_assert((Capacity & (Capacity - 1)) == 0,
                  "Capacity must be a power of 2");
    static_assert(Capacity >= 2,
                  "Capacity must be at least 2");
    static_assert(std::is_trivially_copyable_v<T>,
                  "T must be trivially copyable for safe cross-thread transfer");

public:
    SpscRingBuffer()  = default;
    ~SpscRingBuffer() = default;

    // Non-copyable, non-movable (owns atomics).
    SpscRingBuffer(const SpscRingBuffer&)            = delete;
    SpscRingBuffer& operator=(const SpscRingBuffer&) = delete;
    SpscRingBuffer(SpscRingBuffer&&)                 = delete;
    SpscRingBuffer& operator=(SpscRingBuffer&&)      = delete;

    // ----------------------------------------------------------------
    // push(item) — called by the PRODUCER thread only.
    // Returns true if the item was enqueued, false if the buffer is full.
    // ----------------------------------------------------------------
    [[nodiscard]] bool push(const T& item) noexcept {
        const std::size_t t = tail_.load(std::memory_order_relaxed);
        const std::size_t h = head_.load(std::memory_order_acquire);

        // Full check: distance between tail and head equals Capacity.
        if ((t - h) >= Capacity) [[unlikely]] {
            return false;
        }

        buffer_[t & kMask] = item;

        // Release: ensures the element write is visible before tail_ update.
        tail_.store(t + 1, std::memory_order_release);
        return true;
    }

    // ----------------------------------------------------------------
    // pop(item) — called by the CONSUMER thread only.
    // Returns true and fills 'item' if an element was dequeued.
    // Returns false if the buffer is empty.
    // ----------------------------------------------------------------
    [[nodiscard]] bool pop(T& item) noexcept {
        const std::size_t h = head_.load(std::memory_order_relaxed);
        const std::size_t t = tail_.load(std::memory_order_acquire);

        // Empty check.
        if (h == t) [[unlikely]] {
            return false;
        }

        item = buffer_[h & kMask];

        // Release: ensures the element read is complete before head_ update.
        head_.store(h + 1, std::memory_order_release);
        return true;
    }

    // ----------------------------------------------------------------
    // Queries (approximate — may be stale across threads)
    // ----------------------------------------------------------------

    /// True if no items are currently available to pop.
    [[nodiscard]] bool empty() const noexcept {
        const std::size_t h = head_.load(std::memory_order_acquire);
        const std::size_t t = tail_.load(std::memory_order_acquire);
        return h == t;
    }

    /// Approximate number of items currently in the buffer.
    [[nodiscard]] std::size_t size_approx() const noexcept {
        const std::size_t t = tail_.load(std::memory_order_acquire);
        const std::size_t h = head_.load(std::memory_order_acquire);
        return t - h;
    }

    /// Maximum number of items the buffer can hold simultaneously.
    [[nodiscard]] static constexpr std::size_t capacity() noexcept {
        return Capacity;
    }

private:
    static constexpr std::size_t kMask = Capacity - 1;

    // Producer-owned cache line
    alignas(64) std::atomic<std::size_t> tail_{0};

    // Consumer-owned cache line
    alignas(64) std::atomic<std::size_t> head_{0};

    // Ring buffer storage
    T buffer_[Capacity]{};
};
#ifdef _MSC_VER
#pragma warning(pop)
#endif
} // namespace chronosx
