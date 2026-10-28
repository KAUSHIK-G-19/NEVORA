"""
NEVORA EV BATTERY MANAGEMENT SYSTEM - ESP32 UDP TELEMETRY EMULATOR
Simulates ESP32 microcontroller broadcasting JSON telemetry over UDP to port 4210

Target IP:   127.0.0.1 (or local broadcast)
UDP Port:    4210
Cadence:     500 ms (2.0 Hz)
Format:      {"v": 792.4, "i": -34.8, "t": 31.2, "soc": 82.5, "soh": 98.4}
"""

import json
import math
import random
import socket
import sys
import time

TARGET_IP = "127.0.0.1"
TARGET_PORT = 4210
CADENCE_SEC = 0.5

def main():
    print("=" * 65)
    print("  NEVORA BMS // ESP32 UDP TELEMETRY EMULATOR")
    print(f"  Target:    {TARGET_IP}:{TARGET_PORT}")
    print(f"  Interval:  500 ms (2.0 Hz)")
    print("=" * 65)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    phase = 0.0
    soc = 84.5
    soh = 98.4
    temp = 31.2
    packet_num = 0

    print("\n[TRANSMITTING UDP] Press Ctrl+C to terminate...\n")

    try:
        while True:
            t_start = time.time()
            phase += 0.06
            packet_num += 1

            # Dynamic battery load cycle
            pack_current = round(-35.0 + math.sin(phase) * 25.0 + math.cos(phase * 2.3) * 10.0, 2)
            ocv = 792.0 + (soc - 50.0) * 0.35
            pack_voltage = round(ocv + (pack_current * 0.055) + random.uniform(-0.15, 0.15), 2)
            
            heat_kw = (pack_current ** 2 * 0.055) / 1000.0
            temp = round(max(26.0, min(55.0, temp + (heat_kw * 0.003) - (temp - 28.0) * 0.0015)), 2)
            
            delta_ah = (pack_current * 0.5) / 3600.0
            soc = round(max(5.0, min(100.0, soc + (delta_ah / 125.0) * 100.0)), 2)
            soh = round(98.40 - ((100.0 - soc) * 0.0015), 2)

            payload = {
                "v": pack_voltage,
                "i": pack_current,
                "t": temp,
                "soc": soc,
                "soh": soh,
            }

            data = json.dumps(payload).encode("utf-8")
            sock.sendto(data, (TARGET_IP, TARGET_PORT))

            print(f"[{packet_num:05d} @ UDP {TARGET_PORT}] -> {payload}")

            elapsed = time.time() - t_start
            sleep_time = max(0.01, CADENCE_SEC - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[STOPPING] UDP simulation ended by user.")
    finally:
        sock.close()

if __name__ == "__main__":
    main()
