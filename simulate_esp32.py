"""
NEVORA EV BATTERY MANAGEMENT SYSTEM - ESP32 TELEMETRY EMULATOR
Simulates ESP32 microcontroller broadcasting JSON telemetry to broker.hivemq.com (500ms cadence)

Topic:   nevora/battery/telemetry
Broker:  broker.hivemq.com:1883
Cadence: 500 ms (2.0 Hz)
"""

import json
import math
import random
import sys
import time
import paho.mqtt.client as mqtt

BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "nevora/battery/telemetry"
CADENCE_SEC = 0.5  # 500 ms

def main():
    print("=" * 65)
    print("  NEVORA BMS // ESP32 HARDWARE TELEMETRY EMULATOR")
    print(f"  Target Broker: {BROKER}:{PORT}")
    print(f"  Topic:         {TOPIC}")
    print(f"  Interval:      500 ms (2 Hz)")
    print("=" * 65)

    client_id = f"nevora-esp32-sim-{random.randint(1000, 9999)}"
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    else:
        client = mqtt.Client(client_id=client_id)

    def on_connect(c, userdata, flags, rc, props=None):
        if rc == 0:
            print(f"[MQTT] Connected successfully as '{client_id}'")
        else:
            print(f"[MQTT] Connection failed with code {rc}")

    client.on_connect = on_connect

    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
    except Exception as e:
        print(f"[ERROR] Could not connect to MQTT broker: {e}")
        sys.exit(1)

    phase = 0.0
    soc = 84.5
    soh = 98.4
    temp = 31.2
    packet_num = 0

    print("\n[TRANSMITTING] Press Ctrl+C to terminate simulation...\n")

    try:
        while True:
            t_start = time.time()
            phase += 0.06
            packet_num += 1

            # Dynamic battery load cycle: oscillating current with regen spikes
            pack_current = round(-35.0 + math.sin(phase) * 25.0 + math.cos(phase * 2.3) * 10.0, 2)
            
            # Voltage sag / rise proportional to current
            ocv = 792.0 + (soc - 50.0) * 0.35
            pack_voltage = round(ocv + (pack_current * 0.055) + random.uniform(-0.15, 0.15), 2)
            
            # Thermal reaction to I^2 * R heating
            heat_kw = (pack_current ** 2 * 0.055) / 1000.0
            temp = round(max(26.0, min(55.0, temp + (heat_kw * 0.003) - (temp - 28.0) * 0.0015)), 2)
            
            # Coulomb counting SoC drain
            delta_ah = (pack_current * 0.5) / 3600.0
            soc = round(max(5.0, min(100.0, soc + (delta_ah / 125.0) * 100.0)), 2)
            
            # Slow SoH micro-decay
            soh = round(98.40 - ((100.0 - soc) * 0.0015), 2)

            payload = {
                "packVoltage": pack_voltage,
                "packCurrent": pack_current,
                "cellTemp": temp,
                "SoC": soc,
                "SoH": soh,
            }

            json_bytes = json.dumps(payload)
            res = client.publish(TOPIC, json_bytes)

            print(f"[{packet_num:05d} @ 500ms] {TOPIC} -> {json_bytes}")

            # Maintain exact 500ms timing
            elapsed = time.time() - t_start
            sleep_time = max(0.01, CADENCE_SEC - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[STOPPING] Simulation ended by user.")
    finally:
        client.loop_stop()
        client.disconnect()
        print("[MQTT] Disconnected.")

if __name__ == "__main__":
    main()
