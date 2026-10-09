#pragma once

#include "cloud_logger.hpp"

#include <atomic>
#include <cstdint>
#include <pthread.h>
#include <string>
#include <thread>

namespace nevora {

struct __attribute__((packed, aligned(8))) NEVORAShmLayout {
    pthread_mutex_t mutex;
    std::uint32_t version{1U};
    std::uint32_t size_bytes{0U};
    std::uint64_t sequence{0U};
    std::uint64_t timestamp_ms{0U};
    float voltage_v{0.0F};
    float current_a{0.0F};
    float temperature_c{0.0F};
    float soc_percent{0.0F};
    float soh_percent{0.0F};
    float rul_cycles{0.0F};
    float degradation_risk{1.0F};
    std::uint8_t fallback_active{1U};
};

class HmiBridge {
public:
    HmiBridge(PinnEngine& engine, CloudLogger& cloud_logger,
              std::string shared_memory_name = "/nevora_bms_shm");
    ~HmiBridge();
    HmiBridge(const HmiBridge&) = delete;
    HmiBridge& operator=(const HmiBridge&) = delete;

    bool start();
    void stop();

private:
    void run();
    bool open_shared_memory();
    void close_shared_memory();
    void publish(const BatterySample& sample, const TwinOutput& output);
    bool lock_shared_memory();

    PinnEngine& engine_;
    CloudLogger& cloud_logger_;
    std::string shared_memory_name_;
    std::atomic<bool> running_{false};
    int shared_memory_fd_{-1};
    NEVORAShmLayout* shared_memory_{nullptr};
    std::thread worker_;
};

} // namespace nevora
