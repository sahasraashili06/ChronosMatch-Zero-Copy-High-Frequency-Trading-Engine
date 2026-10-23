
/**
 * @file spsc_ring_buffer.hpp
 * @brief Lock-free Single-Producer Single-Consumer (SPSC) ring buffer.
 *
 * Design:
 * - Exactly one producer thread and one consumer thread.
 * - Atomic acquire/release operations for synchronization.
 * - Separate cache-line alignment for head_ and tail_ to mitigate
 *   false sharing.
 * - Capacity must be a power of two.
 * - All Capacity slots are usable.
 *
 * Overflow: push() returns false when full.
 * Underflow: pop() returns false when empty.
 *
 * Thread safety:
 * - Do not call push() concurrently from multiple producer threads.
 * - Do not call pop() concurrently from multiple consumer threads.
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

#ifdef _MSC_VER
#pragma warning(push)
#pragma warning(disable : 4324)
#endif

template <typename T, std::size_t Capacity>
class SpscRingBuffer {
    static_assert(Capacity >= 2,
                  "Capacity must be at least 2");

    static_assert((Capacity & (Capacity - 1)) == 0,
                  "Capacity must be a power of 2");

    static_assert(std::is_trivially_copyable_v<T>,
                  "T must be trivially copyable for safe cross-thread transfer");

public:
    SpscRingBuffer() = default;
    ~SpscRingBuffer() = default;

    // Non-copyable and non-movable because the buffer owns atomic counters.
    SpscRingBuffer(const SpscRingBuffer&) = delete;
    SpscRingBuffer& operator=(const SpscRingBuffer&) = delete;
    SpscRingBuffer(SpscRingBuffer&&) = delete;
    SpscRingBuffer& operator=(SpscRingBuffer&&) = delete;

    // Producer thread only.
    // Returns false if the buffer is full.
    [[nodiscard]] bool push(const T& item) noexcept {
        const std::size_t t =
            tail_.load(std::memory_order_relaxed);

        const std::size_t h =
            head_.load(std::memory_order_acquire);

        if ((t - h) >= Capacity) [[unlikely]] {
            return false;
        }

        buffer_[t & kMask] = item;

        // Publish the written element to the consumer.
        tail_.store(t + 1, std::memory_order_release);

        return true;
    }

    // Consumer thread only.
    // Returns false if the buffer is empty.
    [[nodiscard]] bool pop(T& item) noexcept {
        const std::size_t h =
            head_.load(std::memory_order_relaxed);

        const std::size_t t =
            tail_.load(std::memory_order_acquire);

        if (h == t) [[unlikely]] {
            return false;
        }

        item = buffer_[h & kMask];

        // Publish the freed slot to the producer.
        head_.store(h + 1, std::memory_order_release);

        return true;
    }

    // True when no elements are currently available.
    [[nodiscard]] bool empty() const noexcept {
        const std::size_t h =
            head_.load(std::memory_order_acquire);

        const std::size_t t =
            tail_.load(std::memory_order_acquire);

        return h == t;
    }

    // Approximate number of elements currently buffered.
    [[nodiscard]] std::size_t size_approx() const noexcept {
        const std::size_t t =
            tail_.load(std::memory_order_acquire);

        const std::size_t h =
            head_.load(std::memory_order_acquire);

        return t - h;
    }

    // Maximum number of elements the buffer can hold.
    [[nodiscard]] static constexpr std::size_t capacity() noexcept {
        return Capacity;
    }

private:
    static constexpr std::size_t kMask = Capacity - 1;

    // Producer-owned counter on its own cache line.
    alignas(64) std::atomic<std::size_t> tail_{0};

    // Consumer-owned counter on its own cache line.
    alignas(64) std::atomic<std::size_t> head_{0};

    // Fixed-size ring storage.
    T buffer_[Capacity]{};
};

#ifdef _MSC_VER
#pragma warning(pop)
#endif




} // namespace chronosx
