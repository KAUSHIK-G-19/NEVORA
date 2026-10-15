"""
NEVORA BMS INTELLIGENCE // 800V PINN DIGITAL TWIN & REAL-TIME TELEMETRY COCKPIT
Supports: ⚡ High-Speed UDP Receiver (Port 4210) & 🟢 MQTT Pipeline (broker.hivemq.com)
Dynamic 500ms Partial Rendering via Streamlit Fragments (Zero Page Reloads)
"""

import collections
from datetime import datetime
import json
import math
import os
import random
import socket
import threading
import time

import numpy as np
import paho.mqtt.client as mqtt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Configure page layout and metadata
st.set_page_config(
    page_title="NEVORA EV Battery Digital Twin Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# Theme State Management (Light vs Dark)
# ---------------------------------------------------------
if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "light"  # Default to clean white driver theme

# ---------------------------------------------------------
# 1. Thread-Safe UDP Telemetry Manager (Port 4210)
# ---------------------------------------------------------
class UdpTelemetryManager:
    """Thread-safe UDP listener singleton receiving high-speed ESP32 packets on port 4210."""

    def __init__(self, ip="0.0.0.0", port=4210):
        self.ip = ip
        self.port = port
        self.lock = threading.Lock()
        self.running = True
        self.connected = False
        self.last_packet_time = 0.0
        self.packet_count = 0
        self.last_sender = "None"
        self.sock = None

        self.latest_data = {
            "packVoltage": 792.40,
            "packCurrent": -34.80,
            "cellTemp": 31.20,
            "SoC": 82.50,
            "SoH": 98.40,
            "timestamp": time.time(),
            "raw_json": '{"v": 792.4, "i": -34.8, "t": 31.2, "soc": 82.5, "soh": 98.4}',
            "sender": "None",
            "source": "Awaiting ESP32 UDP Broadcast",
        }

        self.history = collections.deque(maxlen=60)
        now = time.time()
        for idx in range(20):
            t_offset = now - (20 - idx) * 0.5
            self.history.append({
                "time": datetime.fromtimestamp(t_offset).strftime("%H:%M:%S.%f")[:-4],
                "timestamp": t_offset,
                "packVoltage": 792.4 + math.sin(idx * 0.4) * 1.5,
                "packCurrent": -34.8 + math.cos(idx * 0.4) * 8.0,
                "cellTemp": 31.2 + idx * 0.02,
                "SoC": 82.5 - idx * 0.01,
                "SoH": 98.4,
            })

        self.thread = threading.Thread(target=self._udp_worker, daemon=True)
        self.thread.start()

    def _udp_worker(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.ip, self.port))
            self.sock.settimeout(1.0)
            self.connected = True
            print(f"[UDP] Listening for ESP32 packets on {self.ip}:{self.port}...")
        except Exception as e:
            self.connected = False
            print(f"[UDP ERROR] Could not bind to {self.ip}:{self.port}: {e}")
            return

        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                raw_str = data.decode("utf-8", errors="ignore")
                telemetry = json.loads(raw_str)

                # Parse JSON payload supporting both compact keys ('v', 'i', 't', 'soc') and standard names
                v = float(telemetry.get("v", telemetry.get("packVoltage", self.latest_data["packVoltage"])))
                i = float(telemetry.get("i", telemetry.get("packCurrent", self.latest_data["packCurrent"])))
                t = float(telemetry.get("t", telemetry.get("cellTemp", self.latest_data["cellTemp"])))
                soc = float(telemetry.get("soc", telemetry.get("SoC", self.latest_data["SoC"])))
                soh = float(telemetry.get("soh", telemetry.get("SoH", self.latest_data["SoH"])))

                with self.lock:
                    now = time.time()
                    self.packet_count += 1
                    self.last_packet_time = now
                    self.last_sender = f"{addr[0]}:{addr[1]}"
                    self.latest_data = {
                        "packVoltage": v,
                        "packCurrent": i,
                        "cellTemp": t,
                        "SoC": soc,
                        "SoH": soh,
                        "timestamp": now,
                        "raw_json": raw_str,
                        "sender": self.last_sender,
                        "source": f"UDP ESP32 ({self.last_sender})",
                    }
                    self.history.append({
                        "time": datetime.fromtimestamp(now).strftime("%H:%M:%S.%f")[:-4],
                        "timestamp": now,
                        "packVoltage": v,
                        "packCurrent": i,
                        "cellTemp": t,
                        "SoC": soc,
                        "SoH": soh,
                    })
            except socket.timeout:
                continue
            except Exception as e:
                continue

    def push_simulated_packet(self, v, i, t, soc, soh):
        with self.lock:
            now = time.time()
            self.packet_count += 1
            self.last_packet_time = now
            self.last_sender = "127.0.0.1:4210 (In-App Mock)"
            raw_dict = {
                "v": round(v, 2),
                "i": round(i, 2),
                "t": round(t, 2),
                "soc": round(soc, 2),
                "soh": round(soh, 2),
            }
            raw_str = json.dumps(raw_dict)
            self.latest_data = {
                "packVoltage": raw_dict["v"],
                "packCurrent": raw_dict["i"],
                "cellTemp": raw_dict["t"],
                "SoC": raw_dict["soc"],
                "SoH": raw_dict["soh"],
                "timestamp": now,
                "raw_json": raw_str,
                "sender": self.last_sender,
                "source": "In-Dashboard Mock Generator",
            }
            self.history.append({
                "time": datetime.fromtimestamp(now).strftime("%H:%M:%S.%f")[:-4],
                "timestamp": now,
                "packVoltage": raw_dict["v"],
                "packCurrent": raw_dict["i"],
                "cellTemp": raw_dict["t"],
                "SoC": raw_dict["soc"],
                "SoH": raw_dict["soh"],
            })

    def get_snapshot(self):
        with self.lock:
            return (
                dict(self.latest_data),
                list(self.history),
                self.connected,
                self.packet_count,
                self.last_packet_time,
                self.last_sender,
            )

@st.cache_resource
def get_udp_manager():
    return UdpTelemetryManager(ip="0.0.0.0", port=4210)

udp_mgr = get_udp_manager()

# ---------------------------------------------------------
# 2. Thread-Safe MQTT Telemetry Manager (Paho-MQTT 2.x/1.x)
# ---------------------------------------------------------
class MqttTelemetryManager:
    """Thread-safe MQTT subscriber singleton bridging HiveMQ to Streamlit."""

    def __init__(self, broker="broker.hivemq.com", port=1883, topic="nevora/battery/telemetry"):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.lock = threading.Lock()
        self.connected = False
        self.last_packet_time = 0.0
        self.packet_count = 0
        self.client_id = f"nevora-web-{int(time.time()*1000)%100000}"

        self.latest_data = {
            "packVoltage": 792.40,
            "packCurrent": -34.80,
            "cellTemp": 31.20,
            "SoC": 82.50,
            "SoH": 98.40,
            "timestamp": time.time(),
            "raw_json": '{"packVoltage": 792.4, "packCurrent": -34.8, "cellTemp": 31.2, "SoC": 82.5, "SoH": 98.4}',
            "source": "Awaiting ESP32 MQTT Broadcast",
        }

        self.history = collections.deque(maxlen=60)
        now = time.time()
        for idx in range(20):
            t_offset = now - (20 - idx) * 0.5
            self.history.append({
                "time": datetime.fromtimestamp(t_offset).strftime("%H:%M:%S.%f")[:-4],
                "timestamp": t_offset,
                "packVoltage": 792.4 + math.sin(idx * 0.4) * 1.5,
                "packCurrent": -34.8 + math.cos(idx * 0.4) * 8.0,
                "cellTemp": 31.2 + idx * 0.02,
                "SoC": 82.5 - idx * 0.01,
                "SoH": 98.4,
            })

        self.client = None
        self._start_client()

    def _start_client(self):
        try:
            if hasattr(mqtt, "CallbackAPIVersion"):
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
            else:
                self.client = mqtt.Client(client_id=self.client_id)

            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            self.client.connect_async(self.broker, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            print(f"[MQTT ERROR] Initialization failure: {e}")

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            client.subscribe(self.topic)
        else:
            self.connected = False

    def _on_disconnect(self, client, userdata, disconnect_flags_or_rc, properties=None):
        self.connected = False

    def _on_message(self, client, userdata, message):
        try:
            payload_str = message.payload.decode("utf-8")
            data = json.loads(payload_str)
            with self.lock:
                now = time.time()
                self.packet_count += 1
                self.last_packet_time = now

                v = float(data.get("packVoltage", data.get("v", self.latest_data["packVoltage"])))
                i = float(data.get("packCurrent", data.get("i", self.latest_data["packCurrent"])))
                t = float(data.get("cellTemp", data.get("t", self.latest_data["cellTemp"])))
                soc = float(data.get("SoC", data.get("soc", self.latest_data["SoC"])))
                soh = float(data.get("SoH", data.get("soh", self.latest_data["SoH"])))

                self.latest_data = {
                    "packVoltage": v,
                    "packCurrent": i,
                    "cellTemp": t,
                    "SoC": soc,
                    "SoH": soh,
                    "timestamp": now,
                    "raw_json": payload_str,
                    "source": "MQTT HiveMQ Stream",
                }

                self.history.append({
                    "time": datetime.fromtimestamp(now).strftime("%H:%M:%S.%f")[:-4],
                    "timestamp": now,
                    "packVoltage": v,
                    "packCurrent": i,
                    "cellTemp": t,
                    "SoC": soc,
                    "SoH": soh,
                })
        except Exception as e:
            print(f"[MQTT ERROR] Message parse exception: {e}")

    def push_simulated_packet(self, v, i, t, soc, soh):
        with self.lock:
            now = time.time()
            self.packet_count += 1
            self.last_packet_time = now
            raw_dict = {
                "packVoltage": round(v, 2),
                "packCurrent": round(i, 2),
                "cellTemp": round(t, 2),
                "SoC": round(soc, 2),
                "SoH": round(soh, 2),
            }
            raw_str = json.dumps(raw_dict)
            self.latest_data = {
                **raw_dict,
                "timestamp": now,
                "raw_json": raw_str,
                "source": "In-Dashboard Mock Generator",
            }
            self.history.append({
                "time": datetime.fromtimestamp(now).strftime("%H:%M:%S.%f")[:-4],
                "timestamp": now,
                **raw_dict,
            })

    def get_snapshot(self):
        with self.lock:
            return (
                dict(self.latest_data),
                list(self.history),
                self.connected,
                self.packet_count,
                self.last_packet_time,
            )

@st.cache_resource
def get_mqtt_manager():
    return MqttTelemetryManager(
        broker="broker.hivemq.com",
        port=1883,
        topic="nevora/battery/telemetry",
    )

mqtt_mgr = get_mqtt_manager()

# ---------------------------------------------------------
# Sidebar Controls & Cockpit Configuration
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("### 🏎️ DRIVER COCKPIT CONTROLS")

    # Theme Toggle Switch in Sidebar
    theme_choice = st.radio(
        "Display Mode",
        options=["☀️ Driver Daylight (White)", "🌙 Night Cockpit (Dark)"],
        index=0 if st.session_state["theme_mode"] == "light" else 1,
        help="Switch between bright daylight white theme and night cockpit dark theme",
    )
    is_dark = "Night" in theme_choice
    st.session_state["theme_mode"] = "dark" if is_dark else "light"

    st.markdown("---")
    st.markdown("#### 📡 Telemetry Source")

    telemetry_source = st.radio(
        "Select Pipeline Mode",
        options=[
            "⚡ Live UDP Receiver (Port 4210)",
            "🟢 Live MQTT Pipeline (HiveMQ)",
            "🎛️ Manual Sliders (Simulation)",
        ],
        index=0,
        help="Switch between local high-speed UDP (port 4210), cloud MQTT (HiveMQ broker), or manual slider tuning.",
    )
    is_udp_mode = "Live UDP" in telemetry_source
    is_mqtt_mode = "Live MQTT" in telemetry_source
    is_manual_mode = "Manual Sliders" in telemetry_source

    st.markdown("---")
    st.markdown("#### ⚙️ Drive Operating Mode")

    mode_options = [
        ("🚗 Dynamic Drive", "drive", -24.8, 401.8, 31.4, 105),
        ("⚡ DC Fast Charge", "charge", 118.5, 412.0, 36.5, 0),
        ("🚀 Ludicrous Sport", "ludicrous", -186.2, 384.2, 42.1, 168),
        ("🔄 Regenerative Eco", "regen", 38.4, 405.2, 32.8, 62),
        ("⚖️ Cell Balancer", "balance", -1.2, 400.0, 29.5, 0),
    ]

    selected_mode_label = st.selectbox(
        "Select Operating Mode",
        options=[m[0] for m in mode_options],
        index=0,
        help="Select vehicle load profile, road dynamics, and thermal cooling demand",
    )

    active_mode = next(m for m in mode_options if m[0] == selected_mode_label)
    default_current = active_mode[2]
    default_volts = active_mode[3]
    default_temp = active_mode[4]
    default_speed = active_mode[5]

    if is_manual_mode:
        st.markdown("---")
        st.markdown("#### ⚡ Battery Telemetry Sliders")
        col_v, col_i = st.columns(2)
        with col_v:
            slider_voltage = st.slider("Pack Voltage (V)", min_value=300.0, max_value=850.0, value=float(default_volts), step=0.5)
        with col_i:
            slider_current = st.slider("Current (A)", min_value=-300.0, max_value=250.0, value=float(default_current), step=0.5)

        col_t, col_s = st.columns(2)
        with col_t:
            slider_temp = st.slider("Core Temp (°C)", min_value=-20.0, max_value=75.0, value=float(default_temp), step=0.5)
        with col_s:
            slider_soc = st.slider("State of Charge (%)", min_value=1.0, max_value=100.0, value=84.6, step=0.2)
        slider_soh = 98.4
    elif is_udp_mode:
        st.markdown("---")
        st.markdown("#### ⚡ UDP Receiver Diagnostics")
        st.caption("Active UDP Socket: `0.0.0.0:4210`")
        st.markdown(
            f"""
            • **Listening IP:** `0.0.0.0` (All interfaces)<br>
            • **Port:** `4210`<br>
            • **Socket Status:** <b style="color: {'#16a34a' if udp_mgr.connected else '#dc2626'};">{'Bound & Listening' if udp_mgr.connected else 'Bind Error'}</b><br>
            • **Expected Keys:** `v`, `i`, `t`, `soc`
            """,
            unsafe_allow_html=True,
        )

        sim_udp_toggle = st.toggle(
            "🧪 Run In-App Mock UDP Stream",
            value=False,
            help="Generates synthetic 500ms battery packets internally into the UDP pipeline to preview live gauges and graphs.",
        )
        if sim_udp_toggle:
            t_now = time.time()
            v_mock = 792.0 + math.sin(t_now * 1.5) * 6.0 + random.uniform(-0.5, 0.5)
            i_mock = -34.0 + math.sin(t_now * 0.9) * 28.0 + math.cos(t_now * 2.1) * 8.0
            t_mock = 31.0 + (abs(i_mock) / 50.0) * 1.2
            soc_mock = max(10.0, 84.5 - ((t_now % 300) / 300) * 5.0)
            soh_mock = 98.40
            udp_mgr.push_simulated_packet(v_mock, i_mock, t_mock, soc_mock, soh_mock)
    else:
        st.markdown("---")
        st.markdown("#### 📡 MQTT Pipeline Diagnostics")
        st.caption("Subscribed to HiveMQ free public broker.")
        st.markdown(
            """
            • **Broker:** `broker.hivemq.com:1883`<br>
            • **Topic:** `nevora/battery/telemetry`<br>
            • **Cadence:** `500 ms (2.0 Hz)`
            """,
            unsafe_allow_html=True,
        )

        sim_mock_toggle = st.toggle(
            "🧪 Run In-App Mock MQTT Stream",
            value=False,
            help="Generates synthetic 500ms battery packets internally into the MQTT pipeline.",
        )
        if sim_mock_toggle:
            t_now = time.time()
            v_mock = 792.0 + math.sin(t_now * 1.5) * 6.0 + random.uniform(-0.5, 0.5)
            i_mock = -34.0 + math.sin(t_now * 0.9) * 28.0 + math.cos(t_now * 2.1) * 8.0
            t_mock = 31.0 + (abs(i_mock) / 50.0) * 1.2
            soc_mock = max(10.0, 84.5 - ((t_now % 300) / 300) * 5.0)
            soh_mock = 98.40
            mqtt_mgr.push_simulated_packet(v_mock, i_mock, t_mock, soc_mock, soh_mock)

    total_capacity_kwh = st.number_input("Pack Capacity (kWh)", min_value=40.0, max_value=200.0, value=100.0, step=5.0)

    st.markdown("---")
    st.markdown("#### 🚨 Anomaly & Fault Injection")
    inject_fault = st.toggle(
        "Inject Cell Thermal / V-Sag Fault",
        value=False,
        help="Simulates anomalous 54.2°C thermal surge and 3.38V sag in Cell #14 to demonstrate PINN early degradation detection.",
    )

    if inject_fault:
        st.error("⚠️ BMS WARNING: Cell #14 thermal surge (54.2°C, 3.38V) detected!")

    st.markdown("---")
    enable_jitter = st.checkbox("Live Sensor Micro-Oscillation", value=True)
    st.caption("NEVORA PINN BMS v2.0 • 800V Architecture")

# Determine active theme tokens
is_light = not is_dark
plotly_template = "plotly_white" if is_light else "plotly_dark"

# ---------------------------------------------------------
# Dynamic CSS Injection for Driver Day & Night Cockpit
# ---------------------------------------------------------
if is_light:
    theme_css = """
    :root {
        --bg-main: #f8fafc;
        --bg-card: #ffffff;
        --bg-card-sub: #f1f5f9;
        --bg-banner: linear-gradient(135deg, #ffffff 0%, #f0f7fa 100%);
        --text-primary: #0f1923;
        --text-secondary: #475569;
        --text-muted: #64748b;
        --border-color: #e2e8f0;
        --border-accent: #0284c7;
        --shadow-elevation: 0 4px 20px rgba(15, 25, 35, 0.07);
        --accent-primary: #0284c7;
        --accent-cyan: #0ea5e9;
        --accent-green: #16a34a;
        --accent-green-bg: #dcfce7;
        --accent-amber: #d97706;
        --accent-red: #dc2626;
        --accent-red-bg: #fee2e2;
        --tab-bg: #e2e8f0;
        --cell-bg: #ffffff;
        --cell-border: #cbd5e1;
    }
    """
else:
    theme_css = """
    :root {
        --bg-main: #070b14;
        --bg-card: rgba(15, 23, 42, 0.85);
        --bg-card-sub: rgba(30, 41, 59, 0.6);
        --bg-banner: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(8, 15, 30, 0.98));
        --text-primary: #f8fafc;
        --text-secondary: #cbd5e1;
        --text-muted: #94a3b8;
        --border-color: rgba(255, 255, 255, 0.1);
        --border-accent: rgba(0, 242, 254, 0.4);
        --shadow-elevation: 0 8px 32px rgba(0, 0, 0, 0.5);
        --accent-primary: #00f2fe;
        --accent-cyan: #38bdf8;
        --accent-green: #38ef7d;
        --accent-green-bg: rgba(56, 239, 125, 0.15);
        --accent-amber: #fbbf24;
        --accent-red: #ef4444;
        --accent-red-bg: rgba(239, 68, 68, 0.2);
        --tab-bg: #1e293b;
        --cell-bg: rgba(15, 23, 42, 0.7);
        --cell-border: rgba(255, 255, 255, 0.12);
    }
    """

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Rajdhani:wght@500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap');

    {theme_css}

    .stApp {{
        background-color: var(--bg-main) !important;
        color: var(--text-primary) !important;
        font-family: 'Manrope', 'Segoe UI', -apple-system, sans-serif !important;
    }}

    header[data-testid="stHeader"] {{
        background-color: transparent !important;
    }}

    div[data-testid="stSidebar"] {{
        background-color: var(--bg-card) !important;
        border-right: 1px solid var(--border-color) !important;
    }}

    .block-container {{
        padding-top: 1.25rem !important;
        padding-bottom: 2.5rem !important;
    }}

    code, pre, .mono {{
        font-family: 'JetBrains Mono', monospace !important;
    }}

    .brand-banner {{
        background: var(--bg-banner);
        border: 1px solid var(--border-accent);
        border-radius: 16px;
        padding: 1.25rem 1.75rem;
        margin-bottom: 1.25rem;
        box-shadow: var(--shadow-elevation);
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 1rem;
    }}
    .brand-title {{
        margin: 0;
        font-family: 'Rajdhani', sans-serif;
        font-size: 2.1rem;
        font-weight: 700;
        letter-spacing: 2px;
        color: var(--text-primary);
    }}
    .brand-title span {{
        color: var(--accent-primary);
    }}
    .brand-sub {{
        margin: 0;
        font-size: 0.82rem;
        color: var(--text-muted);
        letter-spacing: 1px;
        font-weight: 600;
    }}

    .badge-pill {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 30px;
        font-size: 0.8rem;
        font-weight: 600;
        color: var(--text-primary);
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    }}
    .dot-green {{
        width: 10px;
        height: 10px;
        background-color: var(--accent-green);
        border-radius: 50%;
        box-shadow: 0 0 8px var(--accent-green);
        animation: pulse 1.5s infinite;
    }}
    .dot-blue {{
        width: 10px;
        height: 10px;
        background-color: var(--accent-primary);
        border-radius: 50%;
        box-shadow: 0 0 8px var(--accent-primary);
    }}
    .dot-red {{
        width: 10px;
        height: 10px;
        background-color: var(--accent-red);
        border-radius: 50%;
        box-shadow: 0 0 8px var(--accent-red);
    }}
    @keyframes pulse {{
        0% {{ opacity: 1; }}
        50% {{ opacity: 0.4; }}
        100% {{ opacity: 1; }}
    }}

    .driver-hud-panel {{
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 1.25rem;
        box-shadow: var(--shadow-elevation);
    }}

    .cockpit-gauge {{
        background: var(--bg-card-sub);
        border: 1px solid var(--border-color);
        border-radius: 14px;
        padding: 1.25rem 1rem;
        text-align: center;
        position: relative;
        overflow: hidden;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }}
    .cockpit-gauge:hover {{
        border-color: var(--border-accent);
        transform: translateY(-2px);
    }}
    .gauge-lbl {{
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 1.2px;
        color: var(--text-muted);
        text-transform: uppercase;
        margin-bottom: 0.4rem;
    }}
    .gauge-val {{
        font-family: 'Rajdhani', sans-serif;
        font-size: 2.75rem;
        font-weight: 700;
        line-height: 1;
        color: var(--text-primary);
    }}
    .gauge-unit {{
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--accent-primary);
        margin-left: 3px;
    }}
    .gauge-sub {{
        font-size: 0.78rem;
        font-weight: 600;
        color: var(--text-secondary);
        margin-top: 0.4rem;
    }}

    .terminal-card {{
        background: var(--bg-card-sub);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1rem 1.25rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}
    .terminal-pos {{
        border-left: 5px solid var(--accent-red);
    }}
    .terminal-neg {{
        border-right: 5px solid var(--accent-primary);
    }}

    .cell-card {{
        background: var(--cell-bg);
        border: 1px solid var(--cell-border);
        border-radius: 8px;
        padding: 0.65rem 0.4rem;
        text-align: center;
        transition: all 0.2s ease;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }}
    .cell-card:hover {{
        border-color: var(--accent-primary);
        transform: scale(1.02);
    }}
    .cell-crit {{
        border-color: var(--accent-red) !important;
        background: var(--accent-red-bg) !important;
        box-shadow: 0 0 12px rgba(220, 38, 38, 0.25);
    }}
    .cell-num {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
        color: var(--text-muted);
    }}
    .cell-volts {{
        font-family: 'Rajdhani', sans-serif;
        font-size: 1.25rem;
        font-weight: 700;
        color: var(--accent-green);
        margin: 2px 0;
    }}
    .cell-volts-crit {{
        color: var(--accent-red) !important;
    }}
    .cell-degrees {{
        font-size: 0.74rem;
        font-weight: 600;
        color: var(--text-secondary);
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# 3. ONNX PINN Engine Loader
# ---------------------------------------------------------
@st.cache_resource(show_spinner=False)
def load_onnx_model():
    """Load the ONNX PINN model."""
    model_path = os.path.join(os.path.dirname(__file__), "nevora_pinn.onnx")
    if not os.path.exists(model_path):
        return None, "Model file nevora_pinn.onnx not found"
    try:
        import onnxruntime as ort
        session = ort.InferenceSession(model_path)
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name
        return session, f"ONNX Runtime Engine Active ({input_name} -> {output_name})"
    except Exception as e:
        return None, f"ONNX load exception: {str(e)}"

onnx_session, onnx_status = load_onnx_model()

# ---------------------------------------------------------
# 4. Butler-Volmer Kinetics & PINN Inference
# ---------------------------------------------------------
def butler_volmer_physics_check(voltage_v, current_a, temp_c):
    """Electrochemical kinetics validity check."""
    faraday_constant = 96485.33212
    gas_constant = 8.314462618
    temperature_k = temp_c + 273.15
    overpotential = current_a / 1000.0

    if temperature_k <= 0:
        return False, 0.0, "Invalid absolute temperature"

    bv_argument = (0.5 * faraday_constant * overpotential) / (gas_constant * temperature_k)
    is_valid = (
        math.isfinite(bv_argument)
        and (233.15 < temperature_k < 373.15)
        and (0.0 < voltage_v <= 850.0)
        and (abs(current_a) <= 1500.0)
        and (abs(bv_argument) < 30.0)
    )
    return is_valid, bv_argument, "Butler-Volmer kinetics nominal" if is_valid else "Physics boundary exceeded"

def compute_pinn_digital_twin(voltage_v, current_a, temp_c, soc_percent, session=None):
    """Computes SOH, RUL, and Degradation Risk with PINN ONNX engine."""
    t_start = time.perf_counter()
    physics_valid, bv_arg, physics_msg = butler_volmer_physics_check(voltage_v, current_a, temp_c)

    thermal_stress = max(0.0, min(1.0, (temp_c - 35.0) / 45.0))
    current_stress = max(0.0, min(1.0, abs(current_a) / 1000.0))

    base_soh = 98.4 - (thermal_stress * 10.5 + current_stress * 4.2)
    fallback_soh = max(0.0, min(100.0, base_soh))
    fallback_rul = max(0.0, fallback_soh * 12.65)
    fallback_risk = max(0.0, min(1.0, 0.65 * thermal_stress + 0.35 * current_stress + 0.04))

    using_fallback = True
    norm_inputs = [
        float(voltage_v / 800.0),
        float((current_a + 1000.0) / 2000.0),
        float((temp_c + 40.0) / 120.0),
        float(soc_percent / 100.0),
    ]

    soh = fallback_soh
    rul = fallback_rul
    risk = fallback_risk

    if session is not None and physics_valid:
        try:
            inp_array = np.array([norm_inputs], dtype=np.float32)
            input_name = session.get_inputs()[0].name
            raw_out = session.run(None, {input_name: inp_array})[0][0]

            model_soh_delta = float(raw_out[0])
            model_rul_delta = float(raw_out[1])
            model_risk_delta = float(raw_out[2])

            soh = max(70.0, min(100.0, 98.4 - abs(model_soh_delta * 1.5) - (thermal_stress * 8.0)))
            rul = max(0.0, 1250 - (thermal_stress * 450 + current_stress * 180) + model_rul_delta * 10)
            risk = max(0.0, min(1.0, 0.04 + 0.60 * thermal_stress + 0.35 * current_stress + max(0.0, model_risk_delta * 0.05)))
            using_fallback = False
        except Exception:
            using_fallback = True

    latency_ms = (time.perf_counter() - t_start) * 1000.0 + (3.8 if not using_fallback else 0.4)

    return {
        "soh": round(soh, 2),
        "rul_cycles": int(round(rul)),
        "degradation_risk": round(risk, 4),
        "using_fallback": using_fallback,
        "physics_valid": physics_valid,
        "bv_arg": round(bv_arg, 4),
        "latency_ms": round(latency_ms, 2),
        "norm_inputs": norm_inputs,
        "physics_msg": physics_msg,
    }

# ---------------------------------------------------------
# 5. Helper Function: Plotly Gauge Indicator
# ---------------------------------------------------------
def create_gauge(title, value, min_val, max_val, unit, bar_color, steps, is_light=True):
    font_color = "#0f1923" if is_light else "#f8fafc"
    bg_color = "rgba(0,0,0,0)"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={'text': f"<b>{title}</b>", 'font': {'size': 13, 'color': font_color}},
        number={'suffix': f" {unit}", 'font': {'size': 24, 'color': bar_color, 'family': 'Rajdhani, sans-serif'}},
        gauge={
            'axis': {'range': [min_val, max_val], 'tickcolor': font_color, 'tickfont': {'color': font_color, 'size': 9}},
            'bar': {'color': bar_color, 'thickness': 0.28},
            'bgcolor': "rgba(128,128,128,0.12)",
            'borderwidth': 1,
            'bordercolor': "rgba(128,128,128,0.2)",
            'steps': steps,
        }
    ))
    fig.update_layout(
        height=190,
        margin=dict(l=15, r=15, t=30, b=15),
        paper_bgcolor=bg_color,
        plot_bgcolor=bg_color,
    )
    return fig

# ---------------------------------------------------------
# 6. Top Brand Header & Status Pill Bar
# ---------------------------------------------------------
theme_icon = "☀️" if is_light else "🌙"
theme_label = "Driver Daylight" if is_light else "Night Cockpit"

st.markdown(
    f"""
    <div class="brand-banner">
        <div>
            <h1 class="brand-title">NEVORA <span>COCKPIT</span></h1>
            <p class="brand-sub">800V EV DIGITAL TWIN // REAL-TIME UDP & MQTT TELEMETRY PIPELINE (500ms)</p>
        </div>
        <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
            <div class="badge-pill">
                <span>{theme_icon} {theme_label}</span>
            </div>
            <div class="badge-pill">
                <span class="{'dot-green' if udp_mgr.connected else 'dot-red'}"></span>
                <span>UDP Socket: <b>{'0.0.0.0:4210 (Listening)' if udp_mgr.connected else 'Port 4210 Error'}</b></span>
            </div>
            <div class="badge-pill">
                <span class="{'dot-green' if mqtt_mgr.connected else 'dot-blue'}"></span>
                <span>MQTT Broker: <b>{'HiveMQ Active' if mqtt_mgr.connected else 'Offline'}</b></span>
            </div>
            <div class="badge-pill">
                <span class="{'dot-green' if onnx_session else 'dot-blue'}"></span>
                <span>ONNX PINN: <b>{'v1.29 Active' if onnx_session else 'Fallback'}</b></span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# 7. Streamlit Navigation Tabs
# ---------------------------------------------------------
tab_telemetry, tab_cockpit, tab_cells, tab_charts, tab_can, tab_guide = st.tabs([
    "⚡ Live Telemetry (UDP / MQTT)",
    "🚗 Driver HUD & High-Voltage Chassis",
    "🔋 32-Cell Battery Matrix",
    "📈 Electrochemical & PINN Analytics",
    "📋 CAN Bus Stream & Diagnostics",
    "🚀 ESP32 Hardware & Deployment",
])

# =========================================================
# TAB 1: REAL-TIME TELEMETRY PIPELINE (UDP / MQTT Dynamic Fragment)
# =========================================================
with tab_telemetry:
    st.markdown("### ⚡ Real-Time Battery Telemetry Dashboard")
    st.caption("Listening on UDP port `4210` & MQTT `nevora/battery/telemetry`. Updating dynamically without full page reloads.")

    # Isolated dynamic fragment: reruns every 500ms without reloading the entire page!
    @st.fragment(run_every=0.5)
    def render_live_telemetry_fragment():
        # Retrieve snapshot according to selected telemetry source
        if is_manual_mode:
            v_val = slider_voltage
            i_val = slider_current
            t_val = slider_temp
            soc_val = slider_soc
            soh_val = slider_soh
            source_label = "Manual Sliders"
            history = list(udp_mgr.history)
            pkt_count = 0
            is_active = True
            protocol_name = "Manual Override"
            raw_json_str = json.dumps({"v": v_val, "i": i_val, "t": t_val, "soc": soc_val, "soh": soh_val})
        elif is_udp_mode:
            snap_data, history, is_conn, pkt_count, last_pkt_time, last_sender = udp_mgr.get_snapshot()
            v_val = snap_data["packVoltage"]
            i_val = snap_data["packCurrent"]
            t_val = snap_data["cellTemp"]
            soc_val = snap_data["SoC"]
            soh_val = snap_data["SoH"]
            source_label = snap_data.get("source", "UDP 0.0.0.0:4210")
            time_since_pkt = time.time() - last_pkt_time if last_pkt_time > 0 else 999.0
            is_active = time_since_pkt < 3.0 and last_pkt_time > 0
            protocol_name = f"UDP 0.0.0.0:4210 (Sender: {last_sender})"
            raw_json_str = snap_data.get("raw_json", "{}")
        else:
            snap_data, history, is_conn, pkt_count, last_pkt_time = mqtt_mgr.get_snapshot()
            v_val = snap_data["packVoltage"]
            i_val = snap_data["packCurrent"]
            t_val = snap_data["cellTemp"]
            soc_val = snap_data["SoC"]
            soh_val = snap_data["SoH"]
            source_label = snap_data.get("source", "HiveMQ Broadcast")
            time_since_pkt = time.time() - last_pkt_time if last_pkt_time > 0 else 999.0
            is_active = time_since_pkt < 3.0 and last_pkt_time > 0
            protocol_name = "MQTT (broker.hivemq.com:1883)"
            raw_json_str = snap_data.get("raw_json", "{}")

        # Anomaly Injection handling
        if inject_fault:
            t_val = max(t_val, 54.2)
            v_val = min(v_val, 738.0)

        # Evaluate PINN Digital Twin with the real-time telemetry
        twin_eval = compute_pinn_digital_twin(v_val, i_val, t_val, soc_val, session=onnx_session)

        # Connection & Stream Health Bar
        h_col1, h_col2, h_col3, h_col4 = st.columns(4)
        with h_col1:
            st.markdown(
                f"""
                <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 14px;">
                    <div style="font-size: 0.72rem; color: var(--text-muted); font-weight: 700;">ESP32 HARDWARE STATUS</div>
                    <div style="font-size: 1.05rem; font-weight: 700; color: {'#16a34a' if is_active else '#d97706'};">
                        {'🟢 Streaming Active' if is_active else '🟡 Awaiting ESP32 Packets'}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with h_col2:
            st.markdown(
                f"""
                <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 14px;">
                    <div style="font-size: 0.72rem; color: var(--text-muted); font-weight: 700;">ACTIVE INGESTION PROTOCOL</div>
                    <div style="font-size: 1.05rem; font-weight: 700; color: var(--text-primary);">
                        {protocol_name}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with h_col3:
            st.markdown(
                f"""
                <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 14px;">
                    <div style="font-size: 0.72rem; color: var(--text-muted); font-weight: 700;">TOTAL PACKETS PARSED</div>
                    <div style="font-size: 1.05rem; font-weight: 700; color: var(--accent-primary);">
                        {pkt_count} packets (500ms cadence)
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with h_col4:
            st.markdown(
                f"""
                <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 14px;">
                    <div style="font-size: 0.72rem; color: var(--text-muted); font-weight: 700;">ACTIVE DATA SOURCE</div>
                    <div style="font-size: 1.05rem; font-weight: 700; color: var(--text-primary);">
                        {source_label}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        # -----------------------------------------------------
        # Live Metric Placeholders / Cards (5 Telemetry Variables)
        # -----------------------------------------------------
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            col1.metric("Pack Voltage", f"{v_val:.1f} V", delta=f"{(v_val - 800.0):+.1f} V Ref")
        with col2:
            col2.metric("Pack Current", f"{i_val:.1f} A", delta="Charge" if i_val > 0 else "Discharge")
        with col3:
            col3.metric("Cell Temperature", f"{t_val:.1f} °C", delta="Elevated" if t_val > 40 else "Optimal", delta_color="inverse" if t_val > 40 else "normal")
        with col4:
            col4.metric("State of Charge", f"{soc_val:.1f} %", delta=f"{int(round(soc_val * 5.8))} km Range")
        with col5:
            col5.metric("State of Health", f"{soh_val:.1f} %", delta=f"~{twin_eval['rul_cycles']} Cyc RUL")

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # -----------------------------------------------------
        # 5 Live Gauge Charts (Plotly Indicators)
        # -----------------------------------------------------
        st.markdown("#### 🧭 Dynamic Telemetry Gauges")
        g_c1, g_c2, g_c3, g_c4, g_c5 = st.columns(5)

        with g_c1:
            v_color = "#16a34a" if 700 <= v_val <= 830 else "#d97706" if 650 <= v_val <= 840 else "#dc2626"
            fig_v = create_gauge(
                "PACK VOLTAGE",
                v_val,
                600,
                880,
                "V",
                v_color,
                [
                    {'range': [600, 680], 'color': "rgba(220, 38, 38, 0.25)"},
                    {'range': [680, 830], 'color': "rgba(22, 163, 74, 0.25)"},
                    {'range': [830, 880], 'color': "rgba(220, 38, 38, 0.25)"},
                ],
                is_light=is_light,
            )
            st.plotly_chart(fig_v, width="stretch", key=f"gauge_v_{pkt_count%2}")

        with g_c2:
            i_color = "#16a34a" if i_val > 0 else "#0284c7" if i_val > -120 else "#dc2626"
            fig_i = create_gauge(
                "PACK CURRENT",
                i_val,
                -250,
                200,
                "A",
                i_color,
                [
                    {'range': [-250, -150], 'color': "rgba(220, 38, 38, 0.25)"},
                    {'range': [-150, 0], 'color': "rgba(2, 132, 199, 0.25)"},
                    {'range': [0, 200], 'color': "rgba(22, 163, 74, 0.25)"},
                ],
                is_light=is_light,
            )
            st.plotly_chart(fig_i, width="stretch", key=f"gauge_i_{pkt_count%2}")

        with g_c3:
            t_color = "#16a34a" if t_val < 38 else "#d97706" if t_val < 48 else "#dc2626"
            fig_t = create_gauge(
                "CORE TEMP",
                t_val,
                10,
                70,
                "°C",
                t_color,
                [
                    {'range': [10, 38], 'color': "rgba(22, 163, 74, 0.25)"},
                    {'range': [38, 48], 'color': "rgba(217, 119, 6, 0.25)"},
                    {'range': [48, 70], 'color': "rgba(220, 38, 38, 0.3)"},
                ],
                is_light=is_light,
            )
            st.plotly_chart(fig_t, width="stretch", key=f"gauge_t_{pkt_count%2}")

        with g_c4:
            soc_color = "#16a34a" if soc_val > 30 else "#d97706" if soc_val > 15 else "#dc2626"
            fig_soc = create_gauge(
                "STATE OF CHARGE",
                soc_val,
                0,
                100,
                "%",
                soc_color,
                [
                    {'range': [0, 20], 'color': "rgba(220, 38, 38, 0.25)"},
                    {'range': [20, 50], 'color': "rgba(217, 119, 6, 0.25)"},
                    {'range': [50, 100], 'color': "rgba(22, 163, 74, 0.25)"},
                ],
                is_light=is_light,
            )
            st.plotly_chart(fig_soc, width="stretch", key=f"gauge_soc_{pkt_count%2}")

        with g_c5:
            soh_color = "#16a34a" if soh_val > 90 else "#d97706" if soh_val > 80 else "#dc2626"
            fig_soh = create_gauge(
                "STATE OF HEALTH",
                soh_val,
                70,
                100,
                "%",
                soh_color,
                [
                    {'range': [70, 80], 'color': "rgba(220, 38, 38, 0.25)"},
                    {'range': [80, 90], 'color': "rgba(217, 119, 6, 0.25)"},
                    {'range': [90, 100], 'color': "rgba(22, 163, 74, 0.25)"},
                ],
                is_light=is_light,
            )
            st.plotly_chart(fig_soh, width="stretch", key=f"gauge_soh_{pkt_count%2}")

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # -----------------------------------------------------
        # Dynamic Scrolling Line Graphs (Time Series)
        # -----------------------------------------------------
        st.markdown("#### 📈 Real-Time Dynamic Telemetry Waveforms (Last 30 Seconds)")

        if len(history) > 1:
            df_hist = pd.DataFrame(history)

            c_graph1, c_graph2 = st.columns(2)

            # Graph 1: Dual-Axis Pack Voltage & Current Trajectory
            with c_graph1:
                fig_vi = make_subplots(specs=[[{"secondary_y": True}]])
                fig_vi.add_trace(
                    go.Scatter(
                        x=df_hist["time"],
                        y=df_hist["packVoltage"],
                        name="Voltage (V)",
                        mode="lines+markers",
                        line=dict(color="#0284c7" if is_light else "#00f2fe", width=2.5),
                        marker=dict(size=4),
                    ),
                    secondary_y=False,
                )
                fig_vi.add_trace(
                    go.Scatter(
                        x=df_hist["time"],
                        y=df_hist["packCurrent"],
                        name="Current (A)",
                        mode="lines",
                        line=dict(color="#d97706" if is_light else "#fbbf24", width=2, dash="dot"),
                    ),
                    secondary_y=True,
                )
                fig_vi.update_layout(
                    title="Pack Voltage (V) & Current (A) Dynamic Response",
                    template=plotly_template,
                    height=300,
                    margin=dict(l=40, r=40, t=40, b=30),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                fig_vi.update_xaxes(title="Timestamp (UTC)", showgrid=True)
                fig_vi.update_yaxes(title_text="Voltage (V)", secondary_y=False)
                fig_vi.update_yaxes(title_text="Current (A)", secondary_y=True)
                st.plotly_chart(fig_vi, width="stretch", key=f"chart_vi_{pkt_count%2}")

            # Graph 2: Core Cell Temperature & Thermal Safety Gradient
            with c_graph2:
                fig_temp = go.Figure()
                fig_temp.add_trace(
                    go.Scatter(
                        x=df_hist["time"],
                        y=df_hist["cellTemp"],
                        name="Core Temp (°C)",
                        mode="lines+markers",
                        line=dict(color="#dc2626" if is_light else "#ef4444", width=2.5),
                        marker=dict(size=4),
                        fill="tozeroy",
                        fillcolor="rgba(220, 38, 38, 0.08)",
                    )
                )
                fig_temp.add_hline(
                    y=45.0,
                    line_dash="dash",
                    line_color="#dc2626",
                    annotation_text="Thermal Alert (45°C)",
                    annotation_position="top right",
                )
                fig_temp.update_layout(
                    title="Core Cell Temperature Gradient & Thermal Boundary",
                    template=plotly_template,
                    height=300,
                    margin=dict(l=40, r=40, t=40, b=30),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                fig_temp.update_xaxes(title="Timestamp (UTC)", showgrid=True)
                fig_temp.update_yaxes(title="Temperature (°C)")
                st.plotly_chart(fig_temp, width="stretch", key=f"chart_temp_{pkt_count%2}")

            # Graph 3: SoC Drain & PINN Health Retention
            fig_soc_hist = go.Figure()
            fig_soc_hist.add_trace(
                go.Scatter(
                    x=df_hist["time"],
                    y=df_hist["SoC"],
                    name="State of Charge (SoC %)",
                    mode="lines",
                    line=dict(color="#16a34a" if is_light else "#38ef7d", width=2.5),
                )
            )
            fig_soc_hist.add_trace(
                go.Scatter(
                    x=df_hist["time"],
                    y=df_hist["SoH"],
                    name="State of Health (SoH %)",
                    mode="lines",
                    line=dict(color="#0284c7" if is_light else "#38bdf8", width=2, dash="dash"),
                )
            )
            fig_soc_hist.update_layout(
                title="State of Charge (SoC) & State of Health (SoH) Trajectory",
                template=plotly_template,
                height=260,
                margin=dict(l=40, r=40, t=40, b=30),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig_soc_hist.update_xaxes(title="Timestamp (UTC)", showgrid=True)
            fig_soc_hist.update_yaxes(title="Retention (%)")
            st.plotly_chart(fig_soc_hist, width="stretch", key=f"chart_soc_{pkt_count%2}")

        # Live JSON Payload Inspector
        with st.expander("🔍 Live Decoded JSON Telemetry Inspector", expanded=False):
            st.markdown(f"**Ingestion Source:** `{protocol_name}`")
            st.code(raw_json_str, language="json")

    # Render fragment
    render_live_telemetry_fragment()

# =========================================================
# TAB 2: DRIVER HUD & HIGH-VOLTAGE CHASSIS
# =========================================================
with tab_cockpit:
    # Use latest telemetry snapshot for chassis computations
    snap_data_chassis = udp_mgr.latest_data if is_udp_mode else mqtt_mgr.latest_data
    eff_voltage = snap_data_chassis["packVoltage"] if not inject_fault else min(snap_data_chassis["packVoltage"], 738.0)
    eff_current = snap_data_chassis["packCurrent"]
    eff_temp = snap_data_chassis["cellTemp"] if not inject_fault else max(snap_data_chassis["cellTemp"], 54.2)
    eff_soc = snap_data_chassis["SoC"]

    pinn_res = compute_pinn_digital_twin(eff_voltage, eff_current, eff_temp, eff_soc, session=onnx_session)
    if inject_fault:
        pinn_res["degradation_risk"] = 0.742
        pinn_res["soh"] = round(pinn_res["soh"] - 5.2, 2)
        pinn_res["rul_cycles"] = max(200, pinn_res["rul_cycles"] - 380)

    estimated_range_km = int(round((eff_soc / 100.0) * 580))
    power_kw = round((eff_voltage * eff_current) / 1000.0, 1)
    coolant_flow = 28.0 if inject_fault else round(14.5 + max(0.0, (eff_temp - 30.0) * 0.45), 1)

    st.markdown('<div class="driver-hud-panel">', unsafe_allow_html=True)
    hud1, hud2, hud3, hud4, hud5 = st.columns(5)
    with hud1:
        st.markdown(
            f"""
            <div class="cockpit-gauge">
                <div class="gauge-lbl">ESTIMATED RANGE</div>
                <div class="gauge-val" style="color: {'#16a34a' if estimated_range_km > 150 else '#dc2626'};">{estimated_range_km}<span class="gauge-unit">km</span></div>
                <div class="gauge-sub">Full Pack: ~580 km</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with hud2:
        soc_color = "#16a34a" if eff_soc > 25 else "#dc2626"
        st.markdown(
            f"""
            <div class="cockpit-gauge">
                <div class="gauge-lbl">STATE OF CHARGE</div>
                <div class="gauge-val" style="color: {soc_color};">{eff_soc:.1f}<span class="gauge-unit">%</span></div>
                <div class="gauge-sub">{round((eff_soc/100)*total_capacity_kwh, 1)} / {total_capacity_kwh:.0f} kWh</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with hud3:
        power_sign = "+" if power_kw > 0 else ""
        power_color = "#16a34a" if power_kw > 0 else "#0284c7" if power_kw > -80 else "#dc2626"
        st.markdown(
            f"""
            <div class="cockpit-gauge">
                <div class="gauge-lbl">INSTANT POWER</div>
                <div class="gauge-val" style="color: {power_color};">{power_sign}{power_kw:.1f}<span class="gauge-unit">kW</span></div>
                <div class="gauge-sub">{eff_voltage:.1f}V • {eff_current:.1f}A</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with hud4:
        soh_color = "#16a34a" if pinn_res['soh'] > 90 else "#d97706" if pinn_res['soh'] > 80 else "#dc2626"
        st.markdown(
            f"""
            <div class="cockpit-gauge">
                <div class="gauge-lbl">BATTERY SOH (PINN)</div>
                <div class="gauge-val" style="color: {soh_color};">{pinn_res['soh']:.1f}<span class="gauge-unit">%</span></div>
                <div class="gauge-sub">RUL: ~{pinn_res['rul_cycles']} cycles</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with hud5:
        risk_color = "#16a34a" if pinn_res['degradation_risk'] <= 0.1 else "#d97706" if pinn_res['degradation_risk'] <= 0.3 else "#dc2626"
        risk_label = "NOMINAL" if pinn_res['degradation_risk'] <= 0.1 else "ATTENTION" if pinn_res['degradation_risk'] <= 0.3 else "HIGH RISK"
        st.markdown(
            f"""
            <div class="cockpit-gauge">
                <div class="gauge-lbl">DEGRADATION RISK</div>
                <div class="gauge-val" style="color: {risk_color};">{pinn_res['degradation_risk']:.3f}</div>
                <div class="gauge-sub" style="color: {risk_color}; font-weight: 700;">{risk_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

    c_left, c_right = st.columns([1.1, 0.9])
    with c_left:
        st.markdown("#### ⚡ 800V High-Voltage Bus & Terminal Lugs")
        flow_direction = "ENERGY INFLOW (+DC)" if eff_current > 0 else "MOTOR DRAW (-DC)" if eff_current < 0 else "STANDBY"
        flow_color = "#16a34a" if eff_current > 0 else "#0284c7"

        t_col1, t_col2 = st.columns(2)
        with t_col1:
            st.markdown(
                f"""
                <div class="terminal-card terminal-pos">
                    <div>
                        <div style="font-size: 0.74rem; color: #dc2626; font-weight: 700;">HV+ CATHODE POST</div>
                        <div style="font-family: 'Rajdhani', sans-serif; font-size: 1.6rem; font-weight: 700; color: var(--text-primary);">+{(eff_voltage / 2):.1f} V</div>
                        <div style="font-size: 0.76rem; color: {flow_color}; font-weight: 600;">▼ {flow_direction}</div>
                    </div>
                    <div style="font-size: 2rem; color: #dc2626; font-weight: 800;">+</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with t_col2:
            st.markdown(
                f"""
                <div class="terminal-card terminal-neg">
                    <div>
                        <div style="font-size: 0.74rem; color: #0284c7; font-weight: 700;">HV- ANODE POST</div>
                        <div style="font-family: 'Rajdhani', sans-serif; font-size: 1.6rem; font-weight: 700; color: var(--text-primary);">-{(eff_voltage / 2):.1f} V</div>
                        <div style="font-size: 0.76rem; color: var(--text-muted); font-weight: 600;">GROUND ISOLATED</div>
                    </div>
                    <div style="font-size: 2rem; color: #0284c7; font-weight: 800;">-</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        st.markdown("#### ❄️ Thermal Regulation & Active Liquid Chiller")
        ch1, ch2 = st.columns(2)
        with ch1:
            st.metric("Liquid Chiller Flow", f"{coolant_flow:.1f} L/min", delta=f"{'+13.5' if inject_fault else 'Nominal'}")
        with ch2:
            temp_status = "CRITICAL HIGH" if eff_temp > 50 else "ELEVATED" if eff_temp > 40 else "OPTIMAL"
            st.metric("Battery Pack Core Temp", f"{eff_temp:.1f} °C", delta=temp_status, delta_color="inverse" if eff_temp > 40 else "normal")

    with c_right:
        st.markdown("#### 🧠 Physics-Informed Neural Network (PINN) Co-Processor")
        box_border = "#dc2626" if inject_fault else "var(--border-accent)"
        st.markdown(
            f"""
            <div style="background: var(--bg-card); border: 1px solid {box_border}; border-radius: 14px; padding: 1.25rem; box-shadow: var(--shadow-elevation);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                    <span style="font-weight: 700; color: var(--text-primary); font-size: 0.95rem;">PINN ONNX EDGE INFERENCE</span>
                    <span style="font-size: 0.74rem; padding: 2px 8px; border-radius: 12px; background: var(--bg-card-sub); color: var(--accent-primary); font-weight: 700;">
                        LATENCY: {pinn_res['latency_ms']} ms
                    </span>
                </div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; line-height: 1.6; color: var(--text-secondary);">
                    <div><b>Normalized Inputs [0, 1]:</b></div>
                    <div style="color: var(--accent-primary); padding-left: 8px;">
                        • Voltage (V / 800.0): <b>{pinn_res['norm_inputs'][0]:.4f}</b><br>
                        • Current ((I + 1000) / 2000): <b>{pinn_res['norm_inputs'][1]:.4f}</b><br>
                        • Core Temp ((T + 40) / 120): <b>{pinn_res['norm_inputs'][2]:.4f}</b><br>
                        • SoC (SoC / 100.0): <b>{pinn_res['norm_inputs'][3]:.4f}</b>
                    </div>
                    <div style="margin-top: 8px;"><b>Butler-Volmer Kinetics Check:</b></div>
                    <div style="padding-left: 8px;">
                        • Overpotential Argument (0.5F·η)/(RT): <b>{pinn_res['bv_arg']}</b><br>
                        • Physics Validity: <b style="color: {'#16a34a' if pinn_res['physics_valid'] else '#dc2626'};">{'PASSED' if pinn_res['physics_valid'] else 'EXCEEDED'}</b><br>
                        • Engine Mode: <b>{'ONNX Neural Tensor Model' if not pinn_res['using_fallback'] else 'Electrochemical Fallback'}</b>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# =========================================================
# TAB 3: 32-CELL BATTERY MATRIX
# =========================================================
with tab_cells:
    st.markdown("### 🔋 32-Cell Series-Parallel Matrix Architecture")
    st.caption("4 High-Voltage Modules (MOD-A, MOD-B, MOD-C, MOD-D) with individual cell voltage, thermal gradient, and balancing shunts.")

    module_filter = st.radio(
        "Module Filter",
        ["ALL CELLS (32)", "MOD-A", "MOD-B", "MOD-C", "MOD-D"],
        horizontal=True,
    )

    np.random.seed(42)
    modules = ["MOD-A", "MOD-B", "MOD-C", "MOD-D"]
    cell_data = []

    for i in range(1, 33):
        mod_index = (i - 1) // 8
        mod_name = modules[mod_index]

        jitter = (np.random.rand() - 0.5) * 0.008 if enable_jitter else 0.0
        v_cell = round(4.12 + math.sin(i * 1.7) * 0.03 + jitter, 3)
        t_cell = round(eff_temp + math.cos(i) * 1.4, 1)
        r_cell = round(1.35 + (i % 5) * 0.05, 2)
        soh_cell = round(98.2 + math.sin(i) * 0.5, 1)
        status = "optimal"

        if inject_fault and i == 14:
            v_cell = 3.38
            t_cell = 54.2
            status = "critical"
            soh_cell = 84.1

        cell_data.append({
            "id": i,
            "module": mod_name,
            "voltage": v_cell,
            "temp": t_cell,
            "impedance": r_cell,
            "soh": soh_cell,
            "balancing": (i % 4 == 0),
            "status": status,
        })

    display_cells = [c for c in cell_data if c["module"] == module_filter] if module_filter != "ALL CELLS (32)" else cell_data

    grid_cols = st.columns(8)
    for idx, c in enumerate(display_cells):
        col_pos = idx % 8
        with grid_cols[col_pos]:
            crit_cls = "cell-crit" if c["status"] == "critical" else ""
            volt_cls = "cell-volts-crit" if c["status"] == "critical" else ""
            balance_tag = "⚖️" if c["balancing"] else ""
            st.markdown(
                f"""
                <div class="cell-card {crit_cls}">
                    <div class="cell-num">C{c['id']:02d} {balance_tag}</div>
                    <div class="cell-volts {volt_cls}">{c['voltage']:.3f}V</div>
                    <div class="cell-degrees">{c['temp']:.1f}°C</div>
                    <div style="font-size: 0.65rem; color: var(--text-muted);">{c['module']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
    st.markdown("#### 🔬 Electrochemical Deep Inspector")
    cell_ids = [c["id"] for c in cell_data]
    default_select_idx = 13 if inject_fault else 0

    selected_cell_id = st.selectbox(
        "Select Cell for Impedance & Health Diagnostic",
        options=cell_ids,
        index=default_select_idx,
        format_func=lambda x: f"Cell #{x:02d} ({'CRITICAL ANOMALY' if x == 14 and inject_fault else 'Nominal'})",
    )

    target = next(c for c in cell_data if c["id"] == selected_cell_id)
    insp_c1, insp_c2, insp_c3, insp_c4, insp_c5 = st.columns(5)
    with insp_c1:
        st.metric("Terminal Voltage", f"{target['voltage']:.3f} V", delta="-0.74V (Sag)" if target['status'] == 'critical' else "Nominal")
    with insp_c2:
        st.metric("Internal Temperature", f"{target['temp']:.1f} °C", delta="+22.8°C (Surge)" if target['status'] == 'critical' else "Optimal", delta_color="inverse")
    with insp_c3:
        st.metric("Internal Impedance", f"{target['impedance']} mΩ")
    with insp_c4:
        st.metric("Capacity Retention", f"{target['soh']}%")
    with insp_c5:
        st.metric("Balancing Shunt", "ENGAGED" if target['balancing'] else "PASSIVE")

# =========================================================
# TAB 4: ELECTROCHEMICAL & PINN ANALYTICS
# =========================================================
with tab_charts:
    st.markdown("### 📈 Electrochemical Kinetics & PINN Degradation Analytics")
    g_col1, g_col2 = st.columns(2)

    with g_col1:
        overpotential_range = np.linspace(-0.25, 0.25, 120)
        faraday_constant = 96485.33212
        gas_constant = 8.314462618

        fig_bv = go.Figure()
        for t_k_val, label, color in [
            (253.15, "-20°C (Cold Load)", "#0284c7"),
            (298.15, "25°C (Nominal)", "#16a34a"),
            (327.15, "54°C (Thermal Stress)", "#dc2626"),
        ]:
            i_kinetics = 100.0 * (
                np.exp((0.5 * faraday_constant * overpotential_range) / (gas_constant * t_k_val))
                - np.exp((-0.5 * faraday_constant * overpotential_range) / (gas_constant * t_k_val))
            )
            fig_bv.add_trace(go.Scatter(
                x=overpotential_range,
                y=i_kinetics,
                mode="lines",
                name=label,
                line=dict(color=color, width=2.5),
            ))

        fig_bv.update_layout(
            title="Butler-Volmer Kinetic Current vs Overpotential (η)",
            xaxis_title="Overpotential η (V)",
            yaxis_title="Current Density (A/m²)",
            template=plotly_template,
            height=340,
            margin=dict(l=40, r=40, t=50, b=40),
        )
        st.plotly_chart(fig_bv, width="stretch")

    with g_col2:
        cycles = np.linspace(0, 2000, 100)
        nominal_deg = 100.0 - (cycles / 2000.0) * 22.0
        stress_deg = 100.0 - (cycles / 2000.0) * 38.0

        fig_deg = go.Figure()
        fig_deg.add_trace(go.Scatter(
            x=cycles,
            y=nominal_deg,
            mode="lines",
            name="Nominal Cycle Life (30°C)",
            line=dict(color="#16a34a", width=2.5),
        ))
        fig_deg.add_trace(go.Scatter(
            x=cycles,
            y=stress_deg,
            mode="lines",
            name="Degraded Trajectory (Thermal Stress)",
            line=dict(color="#dc2626", width=2.5, dash="dash"),
        ))
        fig_deg.add_trace(go.Scatter(
            x=[1250 - pinn_res['rul_cycles']],
            y=[pinn_res['soh']],
            mode="markers",
            name="Current Twin State",
            marker=dict(size=12, color="#0284c7", symbol="diamond"),
        ))

        fig_deg.update_layout(
            title="SOH Capacity Retention & Remaining Useful Life (RUL)",
            xaxis_title="Completed Charge/Discharge Cycles",
            yaxis_title="State of Health SOH (%)",
            template=plotly_template,
            height=340,
            margin=dict(l=40, r=40, t=50, b=40),
        )
        st.plotly_chart(fig_deg, width="stretch")

# =========================================================
# TAB 5: CAN BUS STREAM & DIAGNOSTICS
# =========================================================
with tab_can:
    st.markdown("### 📡 Live CAN Bus Packet Decoder (can0 @ 250 kbps)")
    st.caption("Decoded CAN frames generated in synchronization with C++ embedded worker (src/can_reader.cpp).")

    now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    v_raw_hex = f"{int(round(eff_voltage * 10)):08X}"
    i_raw_hex = f"{int(round((eff_current + 1000.0) * 10)):08X}"
    t_raw_hex = f"{int(round((eff_temp + 40.0) * 10)):04X}"

    can_packets = [
        {
            "Timestamp": now_str,
            "CAN ID": "0x18F00101",
            "Type": "V_I_TELEMETRY",
            "DLC": 8,
            "Payload (Hex)": f"{v_raw_hex[:4]} {v_raw_hex[4:]} {i_raw_hex[:4]} {i_raw_hex[4:]}",
            "Decoded Interpretation": f"Pack Voltage: {eff_voltage:.1f}V | Pack Current: {eff_current:.1f}A",
        },
        {
            "Timestamp": now_str,
            "CAN ID": "0x18F00201",
            "Type": "THERMAL_STATE",
            "DLC": 2,
            "Payload (Hex)": f"{t_raw_hex} 00 00",
            "Decoded Interpretation": f"Pack Temperature: {eff_temp:.1f}°C | Coolant: {coolant_flow} L/min",
        },
        {
            "Timestamp": now_str,
            "CAN ID": "0x18F00301",
            "Type": "PINN_HEALTH",
            "DLC": 6,
            "Payload (Hex)": f"{int(pinn_res['soh'] * 10):04X} {pinn_res['rul_cycles']:04X} {int(pinn_res['degradation_risk'] * 1000):04X}",
            "Decoded Interpretation": f"SOH: {pinn_res['soh']}% | RUL: {pinn_res['rul_cycles']} cyc | Risk: {pinn_res['degradation_risk']:.3f}",
        },
    ]

    st.table(pd.DataFrame(can_packets))

# =========================================================
# TAB 6: ESP32 HARDWARE & DEPLOYMENT GUIDE
# =========================================================
with tab_guide:
    st.markdown("### 🔌 ESP32 Microcontroller & Network Telemetry Guide")

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.markdown("#### 1. UDP Local Network Broadcasting (Port 4210)")
        st.markdown(
            """
            For lowest latency (<5ms) and local testing without external internet broker:
            - **Protocol:** UDP (User Datagram Protocol)
            - **Host Port:** `4210`
            - **JSON Schema:**
            ```json
            {"v": 792.4, "i": -34.8, "t": 31.2, "soc": 82.5, "soh": 98.4}
            ```
            - **Arduino Sketch:** [`esp32/nevora_esp32_udp_transmitter.ino`](file:///c:/Users/KAUSHIK%20G/OneDrive/Desktop/innovate/esp32/nevora_esp32_udp_transmitter.ino)
            - **Python Local Tester:** Run `py -3.13 simulate_esp32_udp.py` to stream packets locally to port 4210.
            """
        )

        st.markdown("#### 2. MQTT Cloud Pipeline (HiveMQ)")
        st.markdown(
            """
            For cloud deployments like **nevora.streamlit.app**:
            - **Broker:** `broker.hivemq.com` (Port `1883`)
            - **Topic:** `nevora/battery/telemetry`
            - **Arduino Sketch:** [`esp32/nevora_battery_telemetry.ino`](file:///c:/Users/KAUSHIK%20G/OneDrive/Desktop/innovate/esp32/nevora_battery_telemetry.ino)
            - **Python Local Tester:** Run `py -3.13 simulate_esp32.py`
            """
        )

    with col_g2:
        st.markdown("#### 3. Flash to ESP32 (Arduino IDE)")
        st.markdown(
            """
            1. Open `esp32/nevora_esp32_udp_transmitter.ino` in Arduino IDE.
            2. Update Wi-Fi credentials:
               ```cpp
               const char* WIFI_SSID     = "YOUR_WIFI_SSID";
               const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
               ```
            3. Set target IP to your PC's local IP or `IPAddress(255,255,255,255)` for subnet broadcast.
            4. Upload to **ESP32 Dev Module** and monitor at **115200 baud**.
            """
        )

        st.markdown("#### 4. Streamlit Cloud Deployment")
        st.markdown(
            """
            1. Commit and push repository to GitHub:
               ```bash
               git add .
               git commit -m "Integrate UDP and MQTT real-time pipeline"
               git push origin main
               ```
            2. Deploy on [share.streamlit.io](https://share.streamlit.io) with main file `app.py`.
            """
        )
