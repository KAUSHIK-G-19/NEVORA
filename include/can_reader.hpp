#pragma once

#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <linux/can.h>
#include <mutex>
#include <string>
#include <thread>

namespace nevora {

struct BatterySample {
    std::chrono::steady_clock::time_point timestamp{};
    float voltage_v{0.0F};
    float current_a{0.0F};
    float temperature_c{0.0F};
    float soc_percent{0.0F};
    std::uint32_t source_id{0U};
    bool valid{false};
};

template <std::size_t Capacity>
class SampleRingBuffer {
public:
    bool push(const BatterySample& sample) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopped_) return false;
        if (size_ == Capacity) {
            tail_ = (tail_ + 1U) % Capacity;
            --size_;
        }
        samples_[head_] = sample;
        head_ = (head_ + 1U) % Capacity;
        ++size_;
        condition_.notify_one();
        return true;
    }

    bool wait_pop(BatterySample& sample, std::chrono::milliseconds timeout) {
        std::unique_lock<std::mutex> lock(mutex_);
        condition_.wait_for(lock, timeout, [this] { return size_ > 0U || stopped_; });
        if (size_ == 0U) return false;
        sample = samples_[tail_];
        tail_ = (tail_ + 1U) % Capacity;
        --size_;
        return true;
    }

    void stop() {
        std::lock_guard<std::mutex> lock(mutex_);
        stopped_ = true;
        condition_.notify_all();
    }

private:
    std::array<BatterySample, Capacity> samples_{};
    std::mutex mutex_;
    std::condition_variable condition_;
    std::size_t head_{0U};
    std::size_t tail_{0U};
    std::size_t size_{0U};
    bool stopped_{false};
};

class CanReader {
public:
    explicit CanReader(SampleRingBuffer<256>& output, std::string interface_name = "can0");
    ~CanReader();
    CanReader(const CanReader&) = delete;
    CanReader& operator=(const CanReader&) = delete;

    bool start();
    void stop();
    std::uint32_t consecutive_drops() const noexcept { return consecutive_drops_.load(); }
    const std::atomic<std::uint32_t>& drop_counter() const noexcept { return consecutive_drops_; }

private:
    void run();
    bool decode(const can_frame& frame, BatterySample& sample);

    SampleRingBuffer<256>& output_;
    std::string interface_name_;
    std::atomic<bool> running_{false};
    std::atomic<std::uint32_t> consecutive_drops_{0U};
    int socket_{-1};
    std::thread worker_;
    BatterySample latest_sample_{};
};

} // namespace nevora
