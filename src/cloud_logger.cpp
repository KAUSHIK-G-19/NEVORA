#include "cloud_logger.hpp"

#include <chrono>
#include <iomanip>
#include <sstream>
#include <utility>

namespace nevora {
CloudLogger::CloudLogger(CloudLoggerConfig config)
    : config_(std::move(config)), client_(config_.server_uri, config_.client_id) {}
CloudLogger::~CloudLogger() { stop(); }

bool CloudLogger::start() {
    if (config_.server_uri.empty() || config_.ca_certificate.empty() ||
        config_.client_certificate.empty() || config_.client_key.empty()) return false;
    try {
        mqtt::connect_options options;
        options.set_clean_session(true);
        options.set_automatic_reconnect(true);
        mqtt::ssl_options ssl;
        ssl.set_trust_store(config_.ca_certificate);
        ssl.set_key_store(config_.client_certificate);
        ssl.set_private_key(config_.client_key);
        options.set_ssl(ssl);
        client_.connect(options)->wait();
        connected_ = true;
        return true;
    } catch (const mqtt::exception&) {
        connected_ = false;
        return false;
    }
}
void CloudLogger::stop() {
    if (!connected_.exchange(false)) return;
    try { client_.disconnect()->wait(); } catch (const mqtt::exception&) {}
}
bool CloudLogger::publish(const BatterySample& sample, const TwinOutput& output) {
    if (!connected_) return false;
    try {
        auto message = mqtt::make_message(config_.topic, make_json(sample, output));
        message->set_qos(1);
        client_.publish(message);
        return true;
    } catch (const mqtt::exception&) {
        connected_ = false;
        return false;
    }
}
std::string CloudLogger::make_json(const BatterySample& sample, const TwinOutput& output) const {
    const auto timestamp_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    std::ostringstream json;
    json << std::fixed << std::setprecision(3)
         << "{\"timestamp_ms\":" << timestamp_ms
         << ",\"voltage_v\":" << sample.voltage_v
         << ",\"current_a\":" << sample.current_a
         << ",\"temperature_c\":" << sample.temperature_c
         << ",\"soc_percent\":" << sample.soc_percent
         << ",\"soh_percent\":" << output.soh_percent
         << ",\"rul_cycles\":" << output.rul_cycles
         << ",\"degradation_risk\":" << output.degradation_risk
         << ",\"fallback\":" << (output.using_fallback ? "true" : "false") << "}";
    return json.str();
}
} // namespace nevora
