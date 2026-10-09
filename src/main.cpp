#include "can_reader.hpp"
#include "cloud_logger.hpp"
#include "hmi_bridge.hpp"
#include "pinn_engine.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <thread>

namespace {
std::atomic<bool> shutdown_requested{false};
void handle_signal(int) { shutdown_requested = true; }
std::string environment_value(const char* name) {
    const char* value = std::getenv(name);
    return value ? value : "";
}
}

int main() {
    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);
    nevora::SampleRingBuffer<256> samples;
    nevora::CanReader can_reader(samples, "can0");
    nevora::PinnEngine pinn_engine(samples, "nevora_pinn.onnx", &can_reader.drop_counter());
    nevora::CloudLoggerConfig cloud_config{
        environment_value("NEVORA_AWS_IOT_ENDPOINT"), "nevora-ev001",
        "nevora/vehicles/EV001/battery/telemetry", environment_value("NEVORA_CA_CERT"),
        environment_value("NEVORA_CLIENT_CERT"), environment_value("NEVORA_CLIENT_KEY")};
    nevora::CloudLogger cloud_logger(cloud_config);
    nevora::HmiBridge hmi_bridge(pinn_engine, cloud_logger);

    if (!pinn_engine.start() || !hmi_bridge.start()) {
        std::cerr << "Failed to start NEVORA inference or IPC workers\n";
        return 1;
    }
    if (!can_reader.start()) std::cerr << "CAN worker did not start; fallback mode remains active\n";
    if (!cloud_logger.start()) std::cerr << "MQTT unavailable; HMI shared memory remains active\n";
    std::cout << "NEVORA running: can0, /nevora_bms_shm, AWS IoT telemetry\n";
    while (!shutdown_requested) std::this_thread::sleep_for(std::chrono::seconds(1));

    can_reader.stop();
    hmi_bridge.stop();
    cloud_logger.stop();
    pinn_engine.stop();
    return 0;
}
