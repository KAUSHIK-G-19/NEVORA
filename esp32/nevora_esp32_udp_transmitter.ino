/*
 * =========================================================================================
 * NEVORA EV BATTERY MANAGEMENT SYSTEM (BMS) - ESP32 UDP TELEMETRY TRANSMITTER
 * Real-Time High-Speed UDP Telemetry to Streamlit Dashboard (Port 4210)
 * =========================================================================================
 * 
 * Hardware:  ESP32 Dev Module / NodeMCU-32S / ESP32-WROOM-32
 * Protocol:  UDP (User Datagram Protocol) - Minimal latency, zero handshake overhead
 * Target IP: Broadcast (255.255.255.255) or Dashboard PC Local IP (e.g., 192.168.1.100)
 * UDP Port:  4210
 * Cadence:   500 ms (2.0 Hz)
 * 
 * JSON Schema:
 *   {
 *     "v": 792.4,   // Pack Voltage (Volts)
 *     "i": -34.8,   // Pack Current (Amperes)
 *     "t": 31.2,    // Core Temp (°C)
 *     "soc": 82.5,  // State of Charge (%)
 *     "soh": 98.4   // State of Health (%)
 *   }
 * =========================================================================================
 */

#include <WiFi.h>
#include <WiFiUdp.h>

// -----------------------------------------------------------------------------
// 1. NETWORK CONFIGURATION
// -----------------------------------------------------------------------------
const char* WIFI_SSID     = "YOUR_WIFI_SSID";         // 2.4 GHz WiFi SSID
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";     // WiFi Password

// Set to your dashboard PC's local IP or IPAddress(255, 255, 255, 255) for subnet broadcast
IPAddress targetIp(255, 255, 255, 255); 
const unsigned int UDP_PORT = 4210;

const unsigned long TELEMETRY_INTERVAL_MS = 500;
unsigned long lastTelemetryTime = 0;
unsigned long lastReconnectAttempt = 0;

WiFiUDP udp;

// Simulated battery parameters
float packVoltage = 792.4;
float packCurrent = -34.8;
float cellTemp    = 31.2;
float stateOfCharge = 82.5;
float stateOfHealth = 98.4;
float simPhase = 0.0;

void setupWiFi() {
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
    Serial.println("\n[WiFi] Connected!");
    Serial.print("[WiFi] Local IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Warning: Connection timeout. Will auto-retry in loop.");
  }
}

void updateBatteryTelemetry() {
  simPhase += 0.05f;
  if (simPhase > 6.283185f) simPhase -= 6.283185f;

  packCurrent = -35.0f + (sin(simPhase) * 22.0f) + (cos(simPhase * 2.3f) * 8.0f);
  float internalResistance = 0.065f;
  float ocv = 790.0f + (stateOfCharge - 50.0f) * 0.4f;
  packVoltage = ocv + (packCurrent * internalResistance) + ((float)(random(-10, 10)) / 100.0f);

  float heatPower = (packCurrent * packCurrent * internalResistance) / 1000.0f;
  cellTemp += (heatPower * 0.002f) - ((cellTemp - 28.0f) * 0.001f);

  float deltaAh = (packCurrent * 0.5f) / 3600.0f;
  stateOfCharge += (deltaAh / 125.0f) * 100.0f;
  if (stateOfCharge < 5.0f) stateOfCharge = 95.0f;
  stateOfHealth = 98.40f - ((100.0f - stateOfCharge) * 0.002f);
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("=====================================================");
  Serial.println("  NEVORA BMS // ESP32 UDP TELEMETRY TRANSMITTER      ");
  Serial.println("  Broadcasting to Port 4210 (500ms cadence)          ");
  Serial.println("=====================================================");

  setupWiFi();
  udp.begin(UDP_PORT);
}

void loop() {
  unsigned long now = millis();

  // Handle WiFi reconnection
  if (WiFi.status() != WL_CONNECTED) {
    if (now - lastReconnectAttempt > 5000) {
      lastReconnectAttempt = now;
      Serial.println("[WiFi] Reconnecting...");
      WiFi.reconnect();
    }
    return;
  }

  // Publish telemetry every 500 ms
  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = now;
    updateBatteryTelemetry();

    char payload[256];
    snprintf(
      payload,
      sizeof(payload),
      "{\"v\":%.2f,\"i\":%.2f,\"t\":%.2f,\"soc\":%.2f,\"soh\":%.2f}",
      packVoltage,
      packCurrent,
      cellTemp,
      stateOfCharge,
      stateOfHealth
    );

    // Send UDP packet
    udp.beginPacket(targetIp, UDP_PORT);
    udp.write((const uint8_t*)payload, strlen(payload));
    udp.endPacket();

    Serial.printf("[UDP 500ms -> Port %d] %s\n", UDP_PORT, payload);
  }
}
