#include "can_reader.hpp"

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <linux/if.h>
#include <linux/can/raw.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>
#include <utility>

namespace nevora {
namespace {
constexpr canid_t kVoltageCurrentId = 0x18F00101U;
constexpr canid_t kTemperatureId = 0x18F00201U;

std::uint32_t read_u32_be(const std::uint8_t* bytes) {
    return (static_cast<std::uint32_t>(bytes[0]) << 24U) |
           (static_cast<std::uint32_t>(bytes[1]) << 16U) |
           (static_cast<std::uint32_t>(bytes[2]) << 8U) |
           static_cast<std::uint32_t>(bytes[3]);
}
std::uint16_t read_u16_be(const std::uint8_t* bytes) {
    return static_cast<std::uint16_t>((static_cast<std::uint16_t>(bytes[0]) << 8U) | bytes[1]);
}
}

CanReader::CanReader(SampleRingBuffer<256>& output, std::string interface_name)
    : output_(output), interface_name_(std::move(interface_name)) {}
CanReader::~CanReader() { stop(); }

bool CanReader::start() {
    bool expected = false;
    if (!running_.compare_exchange_strong(expected, true)) return false;
    worker_ = std::thread(&CanReader::run, this);
    return true;
}

void CanReader::stop() {
    if (!running_.exchange(false)) return;
    if (worker_.joinable()) worker_.join();
    output_.stop();
}

void CanReader::run() {
    socket_ = ::socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (socket_ < 0) { running_ = false; return; }

    ifreq interface_request{};
    std::strncpy(interface_request.ifr_name, interface_name_.c_str(), IFNAMSIZ - 1U);
    if (::ioctl(socket_, SIOCGIFINDEX, &interface_request) < 0) {
        ::close(socket_); socket_ = -1; running_ = false; return;
    }
    sockaddr_can address{};
    address.can_family = AF_CAN;
    address.can_ifindex = interface_request.ifr_ifindex;
    if (::bind(socket_, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) {
        ::close(socket_); socket_ = -1; running_ = false; return;
    }

    pollfd descriptor{socket_, POLLIN, 0};
    while (running_) {
        const int ready = ::poll(&descriptor, 1, 250);
        if (ready < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (ready == 0 || (descriptor.revents & POLLIN) == 0) continue;
        can_frame frame{};
        const ssize_t bytes = ::read(socket_, &frame, sizeof(frame));
        BatterySample sample;
        if (bytes != static_cast<ssize_t>(sizeof(frame)) || !decode(frame, sample)) {
            consecutive_drops_.fetch_add(1U);
            continue;
        }
        consecutive_drops_ = 0U;
        output_.push(sample);
    }
    ::close(socket_);
    socket_ = -1;
}

bool CanReader::decode(const can_frame& frame, BatterySample& sample) {
    const canid_t id = frame.can_id & CAN_EFF_MASK;
    if ((frame.can_id & CAN_EFF_FLAG) == 0U ||
        (id == kVoltageCurrentId && frame.can_dlc < 8U) ||
        (id == kTemperatureId && frame.can_dlc < 2U)) return false;

    latest_sample_.timestamp = std::chrono::steady_clock::now();
    latest_sample_.source_id = id;
    latest_sample_.valid = true;
    if (id == kVoltageCurrentId) {
        latest_sample_.voltage_v = static_cast<float>(read_u32_be(frame.data)) * 0.1F;
        latest_sample_.current_a = static_cast<float>(read_u32_be(frame.data + 4U)) * 0.1F - 1000.0F;
    } else if (id == kTemperatureId) {
        latest_sample_.temperature_c = static_cast<float>(read_u16_be(frame.data)) * 0.1F - 40.0F;
    } else return false;

    latest_sample_.soc_percent = std::clamp(latest_sample_.voltage_v / 800.0F * 100.0F, 0.0F, 100.0F);
    sample = latest_sample_;
    return true;
}

} // namespace nevora
