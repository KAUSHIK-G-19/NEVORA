#include "hmi_bridge.hpp"

#include <cerrno>
#include <chrono>
#include <cstring>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>

namespace nevora {
HmiBridge::HmiBridge(PinnEngine& engine, CloudLogger& cloud_logger, std::string shared_memory_name)
    : engine_(engine), cloud_logger_(cloud_logger), shared_memory_name_(std::move(shared_memory_name)) {}
HmiBridge::~HmiBridge() { stop(); }

bool HmiBridge::start() {
    bool expected = false;
    if (!running_.compare_exchange_strong(expected, true) || !open_shared_memory()) {
        running_ = false; return false;
    }
    worker_ = std::thread(&HmiBridge::run, this);
    return true;
}
void HmiBridge::stop() {
    if (!running_.exchange(false)) { close_shared_memory(); return; }
    if (worker_.joinable()) worker_.join();
    close_shared_memory();
}

bool HmiBridge::open_shared_memory() {
    bool created = false;
    shared_memory_fd_ = ::shm_open(shared_memory_name_.c_str(), O_CREAT | O_EXCL | O_RDWR, 0660);
    if (shared_memory_fd_ < 0 && errno == EEXIST) {
        shared_memory_fd_ = ::shm_open(shared_memory_name_.c_str(), O_RDWR, 0660);
    } else if (shared_memory_fd_ >= 0) {
        created = true;
    }
    if (shared_memory_fd_ < 0 || ::ftruncate(shared_memory_fd_, sizeof(NEVORAShmLayout)) < 0) {
        close_shared_memory(); return false;
    }
    void* mapped = ::mmap(nullptr, sizeof(NEVORAShmLayout), PROT_READ | PROT_WRITE, MAP_SHARED, shared_memory_fd_, 0);
    if (mapped == MAP_FAILED) { close_shared_memory(); return false; }
    shared_memory_ = static_cast<NEVORAShmLayout*>(mapped);

    // Initialize the process-shared robust mutex once for a newly created region.
    if (created) {
        if (shared_memory_->size_bytes != sizeof(NEVORAShmLayout)) {
            std::memset(shared_memory_, 0, sizeof(*shared_memory_));
            pthread_mutexattr_t attributes;
            pthread_mutexattr_init(&attributes);
            pthread_mutexattr_setpshared(&attributes, PTHREAD_PROCESS_SHARED);
            pthread_mutexattr_setrobust(&attributes, PTHREAD_MUTEX_ROBUST);
            pthread_mutex_init(&shared_memory_->mutex, &attributes);
            pthread_mutexattr_destroy(&attributes);
            shared_memory_->version = 1U;
            shared_memory_->size_bytes = sizeof(NEVORAShmLayout);
        }
    }
    return true;
}
void HmiBridge::close_shared_memory() {
    if (shared_memory_) { ::munmap(shared_memory_, sizeof(NEVORAShmLayout)); shared_memory_ = nullptr; }
    if (shared_memory_fd_ >= 0) { ::close(shared_memory_fd_); shared_memory_fd_ = -1; }
}
bool HmiBridge::lock_shared_memory() {
    const int result = pthread_mutex_lock(&shared_memory_->mutex);
    if (result == EOWNERDEAD) { pthread_mutex_consistent(&shared_memory_->mutex); return true; }
    return result == 0;
}
void HmiBridge::run() {
    while (running_) {
        const TwinOutput output = engine_.latest();
        BatterySample sample{};
        sample.voltage_v = output.voltage_v;
        sample.current_a = output.current_a;
        sample.temperature_c = output.temperature_c;
        sample.soc_percent = output.soc_percent;
        sample.valid = output.sequence != 0U;
        publish(sample, output);
        cloud_logger_.publish(sample, output);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}
void HmiBridge::publish(const BatterySample& sample, const TwinOutput& output) {
    if (!shared_memory_ || !lock_shared_memory()) return;
    shared_memory_->sequence = output.sequence;
    shared_memory_->timestamp_ms = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count());
    shared_memory_->voltage_v = sample.voltage_v;
    shared_memory_->current_a = sample.current_a;
    shared_memory_->temperature_c = sample.temperature_c;
    shared_memory_->soc_percent = sample.soc_percent;
    shared_memory_->soh_percent = output.soh_percent;
    shared_memory_->rul_cycles = output.rul_cycles;
    shared_memory_->degradation_risk = output.degradation_risk;
    shared_memory_->fallback_active = output.using_fallback ? 1U : 0U;
    pthread_mutex_unlock(&shared_memory_->mutex);
}
} // namespace nevora
