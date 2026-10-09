#pragma once

#include "pinn_engine.hpp"

#include <atomic>
#include <string>
#include <mqtt/async_client.h>

namespace nevora {

struct CloudLoggerConfig {
    std::string server_uri;
    std::string client_id{"nevora-ev001"};
    std::string topic{"nevora/vehicles/EV001/battery/telemetry"};
    std::string ca_certificate;
    std::string client_certificate;
    std::string client_key;
};

class CloudLogger {
public:
    explicit CloudLogger(CloudLoggerConfig config);
    ~CloudLogger();
    CloudLogger(const CloudLogger&) = delete;
    CloudLogger& operator=(const CloudLogger&) = delete;

    bool start();
    void stop();
    bool publish(const BatterySample& sample, const TwinOutput& output);

private:
    std::string make_json(const BatterySample& sample, const TwinOutput& output) const;
    CloudLoggerConfig config_;
    mqtt::async_client client_;
    std::atomic<bool> connected_{false};
};

} // namespace nevora
