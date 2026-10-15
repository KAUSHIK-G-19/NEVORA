/*
 * =========================================================================================
 * NEVORA EV BATTERY MANAGEMENT SYSTEM (BMS) - ESP32 TELEMETRY TRANSMITTER
 * Real-Time MQTT Telemetry Bridge to Streamlit Digital Twin Dashboard (nevora.streamlit.app)
 * =========================================================================================
 * 
 * Hardware: ESP32 Dev Module / NodeMCU-32S / ESP32-WROOM-32
 * Broker:   broker.hivemq.com (Port 1883)
 * Topic:    nevora/battery/telemetry
 * Cadence:  500 ms (2.0 Hz High-Speed Transmission)
 * 
 * Telemetry Keys:
 *   - packVoltage : Battery pack terminal potential (Volts, e.g., 800V architecture)
 *   - packCurrent : Pack load/charge current (Amperes, positive=charge, negative=discharge)
 *   - cellTemp    : Peak core cell temperature (Celsius)
 *   - SoC         : State of Charge (Percentage, 0-100%)
 *   - SoH         : State of Health (Percentage, 0-100%)
 * 
 * Dependencies (install via Arduino Library Manager):
 *   - PubSubClient by Nick O'Leary
 *   - WiFi (Built into ESP32 core)
 * =========================================================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>

// -----------------------------------------------------------------------------
// 1. NETWORK & MQTT CONFIGURATION
// -----------------------------------------------------------------------------
const char* WIFI_SSID     = "YOUR_WIFI_SSID";         // Replace with your 2.4GHz WiFi SSID
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";     // Replace with your WiFi password

const char* MQTT_BROKER   = "broker.hivemq.com";
const int   MQTT_PORT     = 1883;
const char* MQTT_TOPIC    = "nevora/battery/telemetry";

// Transmission cadence: 500 ms
const unsigned long TELEMETRY_INTERVAL_MS = 500;
unsigned long lastTelemetryTime = 0;
unsigned long lastReconnectAttempt = 0;

// Hardware ADC pins (Optional: connect actual sensors or use synthetic dynamics)
#define PIN_VOLTAGE_ADC  34  // Analog pin for voltage divider
#define PIN_CURRENT_ADC  35  // Analog pin for Hall-effect current shunt
#define PIN_TEMP_ADC     32  // Analog pin for NTC thermistor

// -----------------------------------------------------------------------------
// 2. GLOBAL INSTANCES & CLIENT ID
// -----------------------------------------------------------------------------
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Unique client identifier based on ESP32 MAC address
char clientId[32];

// Simulated battery physics state (drifts realistically if hardware ADC not connected)
float packVoltage = 792.4;    // Nominal 800V battery pack
float packCurrent = -34.8;    // Amperes (Discharging into drivetrain)
float cellTemp    = 31.2;     // Core temperature in Celsius
float stateOfCharge = 82.5;   // SoC percentage
float stateOfHealth = 98.4;   // SoH percentage
float simPhase = 0.0;

// -----------------------------------------------------------------------------
// 3. WIFI INITIALIZATION & MANAGEMENT
// -----------------------------------------------------------------------------
void setupWiFi() {
  delay(10);
  Serial.println();
  Serial.print("[WiFi] Connecting to: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("[WiFi] Connected! IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Warning: Could not connect within 10s. Will auto-retry in loop.");
  }
}

// -----------------------------------------------------------------------------
// 4. MQTT RECONNECT (NON-BLOCKING)
// -----------------------------------------------------------------------------
boolean reconnectMQTT() {
  Serial.print("[MQTT] Connecting to broker: ");
  Serial.print(MQTT_BROKER);
  Serial.print(" as ");
  Serial.println(clientId);

  // Attempt to connect with clean session
  if (mqttClient.connect(clientId)) {
    Serial.println("[MQTT] Connected successfully to HiveMQ broker!");
    return true;
  } else {
    Serial.print("[MQTT] Connect failed, rc=");
    Serial.println(mqttClient.state());
    return false;
  }
}

// -----------------------------------------------------------------------------
// 5. BATTERY SENSOR READING & REALISTIC DYNAMICS
// -----------------------------------------------------------------------------
void updateBatteryTelemetry() {
  // Advance simulation phase for smooth, realistic dynamic EV load profile
  simPhase += 0.05f;
  if (simPhase > 6.283185f) simPhase -= 6.283185f;

  // Realistic load cycle: fluctuating current with occasional regen (+ive spikes)
  // Base current: dynamic discharge oscillating between -15A and -65A
  packCurrent = -35.0f + (sin(simPhase) * 22.0f) + (cos(simPhase * 2.3f) * 8.0f);

  // Pack voltage responds dynamically via internal resistance V = OCV + I * R_int
  float internalResistance = 0.065f; // Ohms
  float ocv = 790.0f + (stateOfCharge - 50.0f) * 0.4f;
  packVoltage = ocv + (packCurrent * internalResistance) + ((float)(random(-10, 10)) / 100.0f);

  // Core temperature reacts slowly to load heat (I^2 * R)
  float heatPower = (packCurrent * packCurrent * internalResistance) / 1000.0f; // kW
  cellTemp += (heatPower * 0.002f) - ((cellTemp - 28.0f) * 0.001f);
  if (cellTemp < 25.0f) cellTemp = 25.0f;
  if (cellTemp > 65.0f) cellTemp = 65.0f;

  // State of charge drains slowly based on energy throughput (Coulomb counting)
  // In 500ms, Ah = Current (A) * (0.5s / 3600s)
  float deltaAh = (packCurrent * 0.5f) / 3600.0f;
  float packCapacityAh = 125.0f; // 100 kWh @ 800V
  stateOfCharge += (deltaAh / packCapacityAh) * 100.0f;
  if (stateOfCharge < 5.0f) stateOfCharge = 95.0f; // Loop for continuous demo
  if (stateOfCharge > 100.0f) stateOfCharge = 100.0f;

  // State of health decays micro-imperceptibly or stays stable
  stateOfHealth = 98.40f - ((100.0f - stateOfCharge) * 0.002f);
}

// -----------------------------------------------------------------------------
// 6. SETUP & MAIN LOOP
// -----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("=====================================================");
  Serial.println("  NEVORA BMS // ESP32 REAL-TIME MQTT TELEMETRY NODE  ");
  Serial.println("  Broadcasting to broker.hivemq.com (500ms cadence)  ");
  Serial.println("=====================================================");

  // Generate unique client ID using ESP32 MAC address
  uint64_t chipId = ESP.getEfuseMac();
  snprintf(clientId, sizeof(clientId), "nevora-esp32-%04X%08X", (uint16_t)(chipId >> 32), (uint32_t)chipId);

  // Setup ADC pin modes (if connecting hardware sensors)
  analogReadResolution(12); // 12-bit ADC (0 - 4095)

  // Configure WiFi and MQTT
  setupWiFi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(512); // Increase buffer for JSON payload
}

void loop() {
  unsigned long now = millis();

  // Ensure WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    if (now - lastReconnectAttempt > 5000) {
      lastReconnectAttempt = now;
      Serial.println("[WiFi] Reconnecting...");
      WiFi.reconnect();
    }
    return;
  }

  // Ensure MQTT connection
  if (!mqttClient.connected()) {
    if (now - lastReconnectAttempt > 3000) {
      lastReconnectAttempt = now;
      if (reconnectMQTT()) {
        lastReconnectAttempt = 0;
      }
    }
  } else {
    mqttClient.loop();
  }

  // Publish telemetry every 500 ms
  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = now;

    // Calculate/read battery parameters
    updateBatteryTelemetry();

    // Format telemetry payload into JSON
    char payload[256];
    snprintf(
      payload,
      sizeof(payload),
      "{\"packVoltage\":%.2f,\"packCurrent\":%.2f,\"cellTemp\":%.2f,\"SoC\":%.2f,\"SoH\":%.2f}",
      packVoltage,
      packCurrent,
      cellTemp,
      stateOfCharge,
      stateOfHealth
    );

    // Publish to HiveMQ broker
    if (mqttClient.connected()) {
      boolean published = mqttClient.publish(MQTT_TOPIC, payload);
      if (published) {
        Serial.print("[PUB 500ms] ");
        Serial.print(MQTT_TOPIC);
        Serial.print(" -> ");
        Serial.println(payload);
      } else {
        Serial.println("[ERROR] Failed to publish MQTT message");
      }
    } else {
      Serial.println("[WARN] MQTT offline, telemetry skipped");
    }
  }
}
