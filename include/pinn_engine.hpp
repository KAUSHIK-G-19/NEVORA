#pragma once

#include "can_reader.hpp"

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

namespace nevora {

struct TwinOutput {
    float voltage_v{0.0F};
    float current_a{0.0F};
    float temperature_c{0.0F};
    float soc_percent{0.0F};
    float soh_percent{0.0F};
    float rul_cycles{0.0F};
    float degradation_risk{1.0F};
    std::uint64_t sequence{0U};
    bool using_fallback{true};
};

class PinnEngine {
public:
    explicit PinnEngine(SampleRingBuffer<256>& input, std::string model_path = "nevora_pinn.onnx",
                        const std::atomic<std::uint32_t>* can_drop_counter = nullptr);
    ~PinnEngine();
    PinnEngine(const PinnEngine&) = delete;
    PinnEngine& operator=(const PinnEngine&) = delete;

    bool start();
    void stop();
    TwinOutput latest() const;

private:
    void run();
    TwinOutput infer(const BatterySample& sample);
    TwinOutput fallback(const BatterySample& sample) const;
    bool physics_constraints_are_valid(const BatterySample& sample, float soh, float risk) const;

    SampleRingBuffer<256>& input_;
    std::string model_path_;
    const std::atomic<std::uint32_t>* can_drop_counter_{nullptr};
    std::atomic<bool> running_{false};
    mutable std::mutex output_mutex_;
    TwinOutput latest_output_{};
    std::thread worker_;
#ifdef NEVORA_HAS_ONNXRUNTIME
    class OnnxState;
    std::unique_ptr<OnnxState> onnx_;
#endif
};

} // namespace nevora
