cmake_minimum_required(VERSION 3.20)
project(nevora_battery LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(ONNXRUNTIME_ROOT "" CACHE PATH "ONNX Runtime aarch64 installation prefix")
set(PAHO_MQTT_CPP_ROOT "" CACHE PATH "Paho MQTT C++ installation prefix")

find_package(Threads REQUIRED)
find_package(PahoMqttCpp CONFIG REQUIRED)

add_executable(nevora_battery
    src/main.cpp
    src/can_reader.cpp
    src/pinn_engine.cpp
    src/hmi_bridge.cpp
    src/cloud_logger.cpp
)
target_include_directories(nevora_battery PRIVATE include)
if(ONNXRUNTIME_ROOT)
    target_include_directories(nevora_battery PRIVATE "${ONNXRUNTIME_ROOT}/include")
    target_link_directories(nevora_battery PRIVATE "${ONNXRUNTIME_ROOT}/lib")
else()
    message(FATAL_ERROR "Set ONNXRUNTIME_ROOT to the aarch64 ONNX Runtime package")
endif()
if(PAHO_MQTT_CPP_ROOT)
    target_include_directories(nevora_battery PRIVATE "${PAHO_MQTT_CPP_ROOT}/include")
    target_link_directories(nevora_battery PRIVATE "${PAHO_MQTT_CPP_ROOT}/lib")
endif()

target_compile_definitions(nevora_battery PRIVATE NEVORA_HAS_ONNXRUNTIME=1)
target_compile_options(nevora_battery PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)
target_link_libraries(nevora_battery PRIVATE onnxruntime PahoMqttCpp::paho-mqttpp3 Threads::Threads rt)
install(TARGETS nevora_battery RUNTIME DESTINATION bin)
