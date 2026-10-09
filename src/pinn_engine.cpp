#include "pinn_engine.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <memory>
#include <utility>

#ifdef NEVORA_HAS_ONNXRUNTIME
#include <onnxruntime_cxx_api.h>
#endif

namespace nevora {
#ifdef NEVORA_HAS_ONNXRUNTIME
class PinnEngine::OnnxState {
public:
    explicit OnnxState(const std::string& path)
        : environment(ORT_LOGGING_LEVEL_WARNING, "nevora"), session_options(), session(make_session(path)) {}
private:
    Ort::Session make_session(const std::string& path) {
        session_options.SetIntraOpNumThreads(1);
        session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_BASIC);
        return Ort::Session(environment, path.c_str(), session_options);
    }
public:
    Ort::Env environment;
    Ort::SessionOptions session_options;
    Ort::Session session;
};
#endif

PinnEngine::PinnEngine(SampleRingBuffer<256>& input, std::string model_path,
                       const std::atomic<std::uint32_t>* can_drop_counter)
    : input_(input), model_path_(std::move(model_path)), can_drop_counter_(can_drop_counter) {}
PinnEngine::~PinnEngine() { stop(); }

bool PinnEngine::start() {
    bool expected = false;
    if (!running_.compare_exchange_strong(expected, true)) return false;
#ifdef NEVORA_HAS_ONNXRUNTIME
    try { onnx_ = std::make_unique<OnnxState>(model_path_); }
    catch (const Ort::Exception&) { onnx_.reset(); }
#endif
    worker_ = std::thread(&PinnEngine::run, this);
    return true;
}
void PinnEngine::stop() {
    if (!running_.exchange(false)) return;
    input_.stop();
    if (worker_.joinable()) worker_.join();
}
TwinOutput PinnEngine::latest() const {
    std::lock_guard<std::mutex> lock(output_mutex_);
    return latest_output_;
}

void PinnEngine::run() {
    while (running_) {
        BatterySample sample;
        if (!input_.wait_pop(sample, std::chrono::milliseconds(250))) continue;
        TwinOutput output = infer(sample);
        if (can_drop_counter_ && can_drop_counter_->load() > 5U) output = fallback(sample);
        output.voltage_v = sample.voltage_v;
        output.current_a = sample.current_a;
        output.temperature_c = sample.temperature_c;
        output.soc_percent = sample.soc_percent;
        std::lock_guard<std::mutex> lock(output_mutex_);
        output.sequence = latest_output_.sequence + 1U;
        latest_output_ = output;
    }
}

TwinOutput PinnEngine::infer(const BatterySample& sample) {
    TwinOutput output = fallback(sample);
#ifdef NEVORA_HAS_ONNXRUNTIME
    if (onnx_) {
        try {
            const float input_values[4] = {
                sample.voltage_v / 800.0F,
                (sample.current_a + 1000.0F) / 2000.0F,
                (sample.temperature_c + 40.0F) / 120.0F,
                sample.soc_percent / 100.0F};
            const std::array<int64_t, 2> shape{1, 4};
            Ort::AllocatorWithDefaultOptions allocator;
            auto input_name = onnx_->session.GetInputNameAllocated(0, allocator);
            const char* input_names[] = {input_name.get()};
            const char* output_names[] = {"soh_output", "rul_output", "degradation_risk"};
            Ort::MemoryInfo memory_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
            auto input_tensor = Ort::Value::CreateTensor<float>(memory_info, const_cast<float*>(input_values), 4,
                                                                 shape.data(), shape.size());
            auto results = onnx_->session.Run(Ort::RunOptions{nullptr}, input_names, &input_tensor, 1,
                                              output_names, 3);
            const float soh_fraction = results[0].GetTensorData<float>()[0];
            const float rul = results[1].GetTensorData<float>()[0];
            const float risk = results[2].GetTensorData<float>()[0];
            if (physics_constraints_are_valid(sample, soh_fraction, risk)) {
                output.soh_percent = std::clamp(soh_fraction, 0.0F, 1.0F) * 100.0F;
                output.rul_cycles = std::max(0.0F, rul);
                output.degradation_risk = std::clamp(risk, 0.0F, 1.0F);
                output.using_fallback = false;
            }
        } catch (const Ort::Exception&) { output = fallback(sample); }
    }
#endif
    return output;
}

TwinOutput PinnEngine::fallback(const BatterySample& sample) const {
    const float thermal_stress = std::clamp((sample.temperature_c - 35.0F) / 45.0F, 0.0F, 1.0F);
    const float current_stress = std::clamp(std::abs(sample.current_a) / 1000.0F, 0.0F, 1.0F);
    TwinOutput output;
    output.soh_percent = std::clamp(sample.soc_percent - thermal_stress * 12.0F - current_stress * 5.0F, 0.0F, 100.0F);
    output.rul_cycles = output.soh_percent * 18.0F;
    output.degradation_risk = std::clamp(0.65F * thermal_stress + 0.35F * current_stress, 0.0F, 1.0F);
    return output;
}

bool PinnEngine::physics_constraints_are_valid(const BatterySample& sample, float soh_fraction, float risk) const {
    constexpr float faraday_constant = 96485.33212F;
    constexpr float gas_constant = 8.314462618F;
    const float temperature_k = sample.temperature_c + 273.15F;
    const float overpotential = sample.current_a / 1000.0F;
    const float butler_volmer_argument = (0.5F * faraday_constant * overpotential) /
                                         (gas_constant * temperature_k);
    return std::isfinite(butler_volmer_argument) && std::isfinite(soh_fraction) && std::isfinite(risk) &&
           temperature_k > 233.15F && temperature_k < 373.15F && sample.voltage_v > 0.0F &&
           sample.voltage_v <= 800.0F && std::abs(sample.current_a) <= 1500.0F &&
           std::abs(butler_volmer_argument) < 30.0F && soh_fraction >= 0.0F && soh_fraction <= 1.0F &&
           risk >= 0.0F && risk <= 1.0F;
}
} // namespace nevora
