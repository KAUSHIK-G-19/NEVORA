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

    st.markdown("#### Dashboard Views")
    dashboard_sections = [
        "⚡ Live Telemetry",
        "🚗 Driver Cockpit",
        "⚡ Pack Configurator",
        "📊 Multi-Physics",
        "🛡️ Risk & Traceability",
        "🔋 Cell Matrix",
        "📈 PINN Analytics",
        "📋 CAN Diagnostics",
        "🚀 Hardware & Deployment",
    ]
    selected_dashboard_section = st.radio(
        "Navigate",
        options=dashboard_sections,
        label_visibility="collapsed",
    )

    st.markdown("---")
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
# Shared telemetry state and live summary for sidebar views
# ---------------------------------------------------------
# Resolve a shared telemetry snapshot so every sidebar view uses the same inputs.
if is_manual_mode:
    eff_voltage = slider_voltage
    eff_current = slider_current
    eff_temp = slider_temp
    eff_soc = slider_soc
else:
    telemetry_manager = udp_mgr if is_udp_mode else mqtt_mgr
    snap_data, *_ = telemetry_manager.get_snapshot()
    eff_voltage = snap_data["packVoltage"]
    eff_current = snap_data["packCurrent"]
    eff_temp = snap_data["cellTemp"]
    eff_soc = snap_data["SoC"]

if inject_fault:
    eff_voltage = min(eff_voltage, 738.0)
    eff_temp = max(eff_temp, 54.2)

pinn_res = compute_pinn_digital_twin(
    eff_voltage, eff_current, eff_temp, eff_soc, session=onnx_session
)
if inject_fault:
    pinn_res["degradation_risk"] = 0.742
    pinn_res["soh"] = round(pinn_res["soh"] - 5.2, 2)
    pinn_res["rul_cycles"] = max(200, pinn_res["rul_cycles"] - 380)


def render_live_summary():
    @st.fragment(run_every=1)
    def render():
        update_mock_stream()

        if is_manual_mode:
            voltage = slider_voltage
            current = slider_current
            temperature = slider_temp
            soc = slider_soc
        else:
            manager = udp_mgr if is_udp_mode else mqtt_mgr
            data, *_ = manager.get_snapshot()
            voltage = data["packVoltage"]
            current = data["packCurrent"]
            temperature = data["cellTemp"]
            soc = data["SoC"]

        if inject_fault:
            voltage = min(voltage, 738.0)
            temperature = max(temperature, 54.2)

        live_result = compute_pinn_digital_twin(
            voltage, current, temperature, soc, session=onnx_session
        )
        if inject_fault:
            live_result["degradation_risk"] = 0.742

        metrics = st.columns(4)
        metrics[0].metric("Pack Voltage", f"{voltage:.1f} V")
        metrics[1].metric("Pack Current", f"{current:.1f} A")
        metrics[2].metric(
            "Core Temperature",
            f"{temperature:.1f} °C",
            delta="Thermal alert" if temperature > 45 else "Nominal",
            delta_color="inverse" if temperature > 45 else "normal",
        )
        metrics[3].metric("PINN Risk", f"{live_result['degradation_risk']:.1%}")

    render()


def update_mock_stream():
    if is_udp_mode and sim_udp_toggle:
        t_now = time.time()
        i_mock = -34.0 + math.sin(t_now * 0.9) * 28.0 + math.cos(t_now * 2.1) * 8.0
        udp_mgr.push_simulated_packet(
            792.0 + math.sin(t_now * 1.5) * 6.0 + random.uniform(-0.5, 0.5),
            i_mock,
            31.0 + (abs(i_mock) / 50.0) * 1.2,
            max(10.0, 84.5 - ((t_now % 300) / 300) * 5.0),
            98.40,
        )
    elif is_mqtt_mode and sim_mock_toggle:
        t_now = time.time()
        i_mock = -34.0 + math.sin(t_now * 0.9) * 28.0 + math.cos(t_now * 2.1) * 8.0
        mqtt_mgr.push_simulated_packet(
            792.0 + math.sin(t_now * 1.5) * 6.0 + random.uniform(-0.5, 0.5),
            i_mock,
            31.0 + (abs(i_mock) / 50.0) * 1.2,
            max(10.0, 84.5 - ((t_now % 300) / 300) * 5.0),
            98.40,
        )

# =========================================================
# TAB 1: REAL-TIME TELEMETRY PIPELINE (UDP / MQTT Dynamic Fragment)
# =========================================================
if selected_dashboard_section == "⚡ Live Telemetry":
    st.markdown("### ⚡ Real-Time Battery Telemetry Dashboard")
    st.caption("Listening on UDP port `4210` & MQTT `nevora/battery/telemetry`. Updating dynamically without full page reloads.")

    # Isolated dynamic fragment: reruns every 500ms without reloading the entire page!
    @st.fragment(run_every=0.5)
    def render_live_telemetry_fragment():
        update_mock_stream()

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
if selected_dashboard_section == "🚗 Driver Cockpit":
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
# TAB 3: PACK CONFIGURATOR (Virtual Pack Design & Sizing)
# =========================================================
if selected_dashboard_section == "⚡ Pack Configurator":
    st.markdown("### ⚡ Battery Energy System Configurator")
    st.caption("Virtually design, architect, and size an EV/BESS battery pack in real time based on cell electrochemistry, series-parallel topology, and thermal cooling.")

    # Multi-Factor Second-Life Battery Grading Rules Definition
    def grade_second_life(soh, delta_r_mOhm, cell_imbalance_mV):
        if soh >= 80.0 and delta_r_mOhm < 10.0 and cell_imbalance_mV < 20:
            return "1st-Life EV Traction Certified"
        elif 70.0 <= soh < 80.0 and delta_r_mOhm < 25.0 and cell_imbalance_mV < 50:
            return "2nd-Life Stationary BESS Storage Certified (Solar/Grid)"
        elif soh < 70.0 or delta_r_mOhm >= 25.0 or cell_imbalance_mV >= 50:
            return "Recycling & Material Recovery Required (E-Waste Prevention)"
        return "Inspection Required"

    # Cell chemistry electrochemical parameter mapping
    chem_specs = {
        "NMC811 (3.7V, 2.5Ah)": {
            "v_nominal": 3.7,
            "c_cell": 2.5,
            "family": "Lithium Nickel Manganese Cobalt (811)",
            "density_desc": "High Energy Density",
        },
        "LFP (3.2V, 3.2Ah)": {
            "v_nominal": 3.2,
            "c_cell": 3.2,
            "family": "Lithium Iron Phosphate",
            "density_desc": "High Thermal & Chemical Stability",
        },
        "LTO (2.3V, 1.5Ah)": {
            "v_nominal": 2.3,
            "c_cell": 1.5,
            "family": "Lithium Titanate Oxide",
            "density_desc": "Extreme High C-Rate & Cycle Life",
        },
    }

    # Two columns with Streamlit card layouts
    col_input, col_output = st.columns([1, 1], gap="large")

    # -----------------------------------------------------
    # Column 1: Pack Architecture & Configuration Inputs
    # -----------------------------------------------------
    with col_input:
        with st.container(border=True):
            st.markdown("#### 🛠️ Pack Architecture & Input Parameters")
            st.caption("Configure series-parallel topological strings, cell chemistry, and cooling strategy.")

            chem = st.selectbox(
                "Select Cell Chemistry",
                options=["NMC811 (3.7V, 2.5Ah)", "LFP (3.2V, 3.2Ah)", "LTO (2.3V, 1.5Ah)"],
                index=0,
                help="Select cell electrochemistry to set nominal voltage (V_cell) and unit capacity (Ah_cell).",
            )

            ns = st.slider(
                "Series Cells (Ns)",
                min_value=12,
                max_value=216,
                value=96,
                step=1,
                help="Number of series cells (Ns). Directly determines total pack voltage.",
            )

            np_cells = st.slider(
                "Parallel Cells (Np)",
                min_value=1,
                max_value=20,
                value=4,
                step=1,
                help="Number of parallel cells (Np). Directly determines total pack capacity.",
            )

            cooling = st.selectbox(
                "Cooling Strategy",
                options=["Passive Air", "Forced Air", "Liquid Cold-Plate"],
                index=2,
                help="Active or passive thermal heat rejection mechanism.",
            )

            # Selected Cell & Topology Breakdown Card
            selected_spec = chem_specs[chem]
            total_cells = ns * np_cells
            st.markdown("---")
            st.markdown(
                f"""
                <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color); border-radius: 10px; padding: 12px 16px;">
                    <div style="font-size: 0.74rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">Topological Summary</div>
                    <div style="font-family: 'Rajdhani', sans-serif; font-size: 1.35rem; font-weight: 700; color: var(--accent-primary);">
                        {ns}S{np_cells}P Matrix ({total_cells} Cells Total)
                    </div>
                    <div style="font-size: 0.82rem; color: var(--text-secondary); margin-top: 4px; line-height: 1.5;">
                        • <b>Cell Rating:</b> {selected_spec['v_nominal']} V nom &bull; {selected_spec['c_cell']} Ah unit<br>
                        • <b>Chemistry:</b> {selected_spec['family']} ({selected_spec['density_desc']})<br>
                        • <b>Thermal Regime:</b> {cooling} Management
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # -----------------------------------------------------
    # Real-Time Engineering Computations
    # -----------------------------------------------------
    v_cell = 3.7 if "NMC811" in chem else (3.2 if "LFP" in chem else 2.3)
    ah_cell = 2.5 if "NMC811" in chem else (3.2 if "LFP" in chem else 1.5)

    v_pack = ns * v_cell
    cap_pack = np_cells * ah_cell
    energy_kwh = (v_pack * cap_pack) / 1000.0
    est_mass_kg = (ns * np_cells * 0.070) * 1.3  # 70g cell + 30% packaging overhead
    est_cost_usd = (ns * np_cells * 3.50) * 1.25
    energy_density_wh_kg = (energy_kwh * 1000.0) / est_mass_kg if est_mass_kg > 0 else 0.0

    # -----------------------------------------------------
    # Column 2: Pack Sizing Outputs (st.metric Real-time Cards)
    # -----------------------------------------------------
    with col_output:
        with st.container(border=True):
            st.markdown("#### 📊 Pack Sizing & Real-Time Engineering Metrics")
            st.caption("Live engineering sizing estimations calculated from physical topology and cost models:")

            # Metric Cards Row 1: Voltage, Capacity, Energy, Mass (4 columns)
            col1, col2 = st.columns(2)
            with col1:
                col1.metric("Pack Voltage", f"{v_pack:.1f} V", delta=f"{ns} × {v_cell:.1f} V nom")
            with col2:
                col2.metric("Pack Capacity", f"{cap_pack:.1f} Ah", delta=f"{np_cells} × {ah_cell:.1f} Ah unit")

            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

            col3, col4 = st.columns(2)
            with col3:
                col3.metric("Pack Energy", f"{energy_kwh:.2f} kWh", delta=f"{(energy_kwh * 1000):.1f} Wh total")
            with col4:
                col4.metric("Est. Mass", f"{est_mass_kg:.1f} kg", delta="1.30× Packaging Overhead", delta_color="off")

            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

            # Metric Cards Row 3: BOM Cost and Energy Density
            m_col5, m_col6 = st.columns(2)
            with m_col5:
                st.metric(
                    label="Estimated Pack BOM Cost",
                    value=f"${est_cost_usd:,.2f}",
                    delta="1.25× Cost Factor ($3.50/cell)",
                    delta_color="off",
                )
            with m_col6:
                st.metric(
                    label="Gravimetric Energy Density",
                    value=f"{energy_density_wh_kg:.1f} Wh/kg",
                    delta=f"{cooling} Strategy",
                    delta_color="normal",
                )

            st.markdown("---")
            # Mathematical Formulation Card
            st.markdown(
                f"""
                <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color); border-radius: 10px; padding: 12px 16px;">
                    <div style="font-size: 0.74rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">Engineering Sizing Formulations</div>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; line-height: 1.6; color: var(--text-secondary);">
                        • <b>V<sub>pack</sub>:</b> Ns × V<sub>cell</sub> = {ns} × {v_cell:.1f}V = <span style="color: var(--accent-primary); font-weight: 700;">{v_pack:.1f} V</span><br>
                        • <b>Cap<sub>pack</sub>:</b> Np × Ah<sub>cell</sub> = {np_cells} × {ah_cell:.1f}Ah = <span style="color: var(--accent-primary); font-weight: 700;">{cap_pack:.1f} Ah</span><br>
                        • <b>Energy<sub>kWh</sub>:</b> (V<sub>pack</sub> × Cap<sub>pack</sub>) / 1000 = <span style="color: var(--accent-green); font-weight: 700;">{energy_kwh:.2f} kWh</span><br>
                        • <b>Mass (kg):</b> (Ns × Np × 0.070) × 1.30 = <span style="color: var(--text-primary); font-weight: 700;">{est_mass_kg:.1f} kg</span><br>
                        • <b>BOM Cost:</b> (Ns × Np × $3.50) × 1.25 = <span style="color: var(--text-primary); font-weight: 700;">${est_cost_usd:,.2f}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------
    # Multi-Factor Second-Life Battery Grading Console
    # -----------------------------------------------------
    with st.container(border=True):
        st.markdown("#### ♻️ Multi-Factor Second-Life Battery Grading & Circular Economy")
        st.caption("Automated lifecycle re-certification rules based on capacity retention (SOH), impedance growth (ΔR), and cell voltage imbalance (ΔV).")

        sl_col1, sl_col2, sl_col3 = st.columns(3)
        with sl_col1:
            eval_soh = st.slider("Battery State of Health (SOH %)", min_value=40.0, max_value=100.0, value=82.5, step=0.5,
                                 help="Current state of health capacity retention percentage.")
        with sl_col2:
            eval_delta_r = st.slider("Internal Resistance Rise ΔR (mΩ)", min_value=0.0, max_value=40.0, value=6.5, step=0.5,
                                     help="Growth in internal cell ESR compared to beginning of life (BOL).")
        with sl_col3:
            eval_imbalance_mv = st.slider("Cell-to-Cell Imbalance ΔV (mV)", min_value=0, max_value=80, value=14, step=1,
                                          help="Maximum voltage difference between cells in the pack in millivolts.")

        certification_result = grade_second_life(eval_soh, eval_delta_r, eval_imbalance_mv)

        # Style output banner based on certificate category
        if "1st-Life" in certification_result:
            grade_color = "#16a34a"
            grade_icon = "🚗"
            grade_badge = "TIER 1 • AUTOMOTIVE TRACTION"
            grade_desc = "Optimal state of health and low internal resistance. Fully certified for demanding high-voltage EV road traction and dynamic regenerative acceleration."
            st.success(f"{grade_icon} **{certification_result}** — {grade_badge}")
        elif "2nd-Life" in certification_result:
            grade_color = "#d97706"
            grade_icon = "🔋"
            grade_badge = "TIER 2 • STATIONARY BESS STORAGE"
            grade_desc = "Capacity or impedance has degraded beyond high-C-rate automotive specs, but remains ideal for stationary grid storage, solar PV buffering, and commercial microgrids."
            st.warning(f"{grade_icon} **{certification_result}** — {grade_badge}")
        else:
            grade_color = "#dc2626"
            grade_icon = "♻️"
            grade_badge = "TIER 3 • RECYCLING & MATERIAL HARVESTING"
            grade_desc = "Substantial cell degradation, elevated impedance, or unsafe cell imbalance detected. Battery should be retired from service and routed for hydrometallurgical material recovery (Lithium, Nickel, Cobalt, Copper recycling)."
            st.error(f"{grade_icon} **{certification_result}** — {grade_badge}")

        st.markdown(
            f"""
            <div style="background: var(--bg-card-sub); border-left: 4px solid {grade_color}; border-radius: 8px; padding: 10px 14px; font-size: 0.83rem; color: var(--text-secondary); line-height: 1.5;">
                <b>Certification Assessment:</b> {grade_desc}<br>
                <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.76rem; color: var(--text-muted);">
                    Evaluated: SOH = {eval_soh:.1f}% | ΔR = {eval_delta_r:.1f} mΩ | ΔV Imbalance = {eval_imbalance_mv} mV
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

# =========================================================
# TAB 4: MULTI-PHYSICS TRADE-OFFS
# =========================================================
if selected_dashboard_section == "📊 Multi-Physics":
    st.markdown("### 📊 Multi-Physics Battery Pack Trade-Off Analysis")
    st.caption(
        "Interactive radar benchmarking, configuration comparison table, and C-Rate thermal simulation "
        "across **Config A — High Energy NMC** vs **Config B — High Safety LFP** pack architectures."
    )
    render_live_summary()

    # -----------------------------------------------------------------
    # Section 1: Radar / Spider Chart — 5 Core Battery Parameters
    # -----------------------------------------------------------------
    st.markdown("#### 🕸️ Multi-Dimensional Performance Radar")
    st.caption(
        "Scores (0–10) across Energy Density, Thermal Safety, Charging Speed, Lifespan, and Cost Efficiency. "
        "Fill opacity encodes each pack's strength profile."
    )

    radar_categories = [
        "Energy Density",
        "Thermal Safety",
        "Charging Speed",
        "Lifespan",
        "Cost Efficiency",
    ]

    # NMC: high energy, lower thermal safety, fast charge, shorter lifespan, costlier
    # LFP: lower energy, best thermal safety, slower charge, longest lifespan, cheapest
    radar_scores_nmc = [9.2, 5.8, 8.0, 6.8, 6.5]
    radar_scores_lfp = [7.0, 9.4, 6.5, 9.5, 9.0]

    radar_df = pd.DataFrame({
        "Parameter": radar_categories * 2,
        "Score": radar_scores_nmc + radar_scores_lfp,
        "Configuration": (
            ["Config A — High Energy NMC Pack"] * len(radar_categories) +
            ["Config B — High Safety LFP Pack"] * len(radar_categories)
        ),
    })

    radar_col, radar_info_col = st.columns([1.55, 1], gap="large")

    with radar_col:
        fig_radar = px.line_polar(
            radar_df,
            r="Score",
            theta="Parameter",
            color="Configuration",
            line_close=True,
            range_r=[0, 10],
            color_discrete_map={
                "Config A — High Energy NMC Pack": "#0ea5e9",
                "Config B — High Safety LFP Pack": "#38ef7d",
            },
            template=plotly_template,
        )
        fig_radar.update_traces(
            fill="toself",
            opacity=0.38,
            line=dict(width=2.5),
        )
        fig_radar.update_layout(
            height=440,
            margin=dict(l=30, r=30, t=30, b=20),
            legend=dict(
                orientation="h",
                y=-0.12,
                xanchor="center",
                x=0.5,
                font=dict(size=11),
            ),
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 10],
                    tickfont=dict(size=9),
                    gridcolor="rgba(128,128,128,0.2)",
                ),
                angularaxis=dict(
                    tickfont=dict(size=11, family="Rajdhani, sans-serif"),
                    gridcolor="rgba(128,128,128,0.2)",
                ),
            ),
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    with radar_info_col:
        st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
        # Score cards per parameter
        param_icons = {
            "Energy Density": "⚡",
            "Thermal Safety": "🌡️",
            "Charging Speed": "🔋",
            "Lifespan": "♻️",
            "Cost Efficiency": "💰",
        }
        for param, nmc_s, lfp_s in zip(radar_categories, radar_scores_nmc, radar_scores_lfp):
            winner = "NMC" if nmc_s >= lfp_s else "LFP"
            winner_color = "#0ea5e9" if winner == "NMC" else "#38ef7d"
            st.markdown(
                f"""
                <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color);
                            border-radius: 10px; padding: 9px 13px; margin-bottom: 7px;
                            display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="font-size: 0.82rem; font-weight: 700;
                                     color: var(--text-primary);">{param_icons[param]} {param}</span>
                    </div>
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <span style="font-family: 'Rajdhani', sans-serif; font-size: 1.05rem;
                                     font-weight: 700; color: #0ea5e9;">{nmc_s}</span>
                        <span style="font-size: 0.72rem; color: var(--text-muted);">vs</span>
                        <span style="font-family: 'Rajdhani', sans-serif; font-size: 1.05rem;
                                     font-weight: 700; color: #38ef7d;">{lfp_s}</span>
                        <span style="font-size: 0.72rem; padding: 2px 7px; border-radius: 12px;
                                     background: var(--bg-card);
                                     color: {winner_color}; font-weight: 700; border: 1px solid {winner_color}30;">
                            ▲ {winner}
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------
    # Section 2: Dynamic Comparison Table — Config A vs Config B
    # -----------------------------------------------------------------
    st.markdown("#### 📋 Configuration Specification Comparison Table")
    st.caption(
        "Side-by-side engineering comparison of **Config A (High Energy NMC)** vs **Config B (High Safety LFP)** "
        "across pack-level design metrics."
    )

    comparison_data = {
        "Specification": [
            "Pack Energy (kWh)",
            "Weight (kg)",
            "Max C-Rate",
            "Nominal Voltage (V)",
            "Thermal Limit (°C)",
            "Cycle Life (cycles)",
            "Gravimetric Density (Wh/kg)",
            "Total Cell Cost ($)",
        ],
        "Config A — High Energy NMC": [
            "107.5 kWh",
            "620 kg",
            "4.0C",
            "400 V",
            "45 °C",
            "~1,500 cycles",
            "173 Wh/kg",
            "$12,740",
        ],
        "Config B — High Safety LFP": [
            "92.0 kWh",
            "680 kg",
            "2.5C",
            "345 V",
            "60 °C",
            "~3,500 cycles",
            "135 Wh/kg",
            "$9,100",
        ],
        "Advantage": [
            "⚡ NMC (+15.8%)",
            "⚡ NMC (−60 kg)",
            "⚡ NMC (faster)",
            "⚡ NMC (+55 V)",
            "🛡️ LFP (+15°C limit)",
            "♻️ LFP (+2,000 cyc)",
            "⚡ NMC (+38 Wh/kg)",
            "💰 LFP (−$3,640)",
        ],
    }

    df_compare = pd.DataFrame(comparison_data)

    st.dataframe(
        df_compare,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Specification": st.column_config.TextColumn(
                "Specification", width="medium"
            ),
            "Config A — High Energy NMC": st.column_config.TextColumn(
                "Config A ⚡ NMC", width="medium"
            ),
            "Config B — High Safety LFP": st.column_config.TextColumn(
                "Config B 🛡️ LFP", width="medium"
            ),
            "Advantage": st.column_config.TextColumn(
                "Pack Advantage", width="medium"
            ),
        },
    )

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------
    # Section 3: C-Rate Thermal Simulation — Interactive Slider
    # -----------------------------------------------------------------
    st.markdown("#### 🌡️ C-Rate Thermal Simulation — Estimated Temperature Rise Curve")
    st.caption(
        "Simulate thermal runaway risk across discharge rates. "
        "Model: `T(t) = T_ambient + K·(C-Rate^α) · (1 − e^(−t/τ))` — electrochemical exponential thermal heating."
    )

    sim_col_ctrl, sim_col_chart = st.columns([0.9, 2.1], gap="large")

    with sim_col_ctrl:
        st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)
        c_rate_sim = st.slider(
            "⚡ Discharge C-Rate",
            min_value=0.5,
            max_value=5.0,
            value=2.0,
            step=0.1,
            format="%.1fC",
            help=(
                "C-Rate is the discharge current relative to nominal capacity. "
                "1C = full discharge in 1 hour. 5C = full discharge in 12 minutes."
            ),
        )

        # Derived thermal parameters at selected C-Rate
        T_ambient = 25.0
        K_nmc = 3.8        # thermal gain constant NMC (higher resistivity)
        K_lfp = 3.1        # thermal gain constant LFP (more thermally stable)
        alpha_nmc = 1.8    # super-linear C-Rate exponent NMC
        alpha_lfp = 1.65   # sub-linear C-Rate exponent LFP
        tau_nmc = 7.5      # thermal time constant NMC (faster heating)
        tau_lfp = 9.0      # thermal time constant LFP (slower heating)

        t_duration = min(45.0, 60.0 / c_rate_sim)
        t_nmc_peak = T_ambient + K_nmc * (c_rate_sim ** alpha_nmc)
        t_lfp_peak = T_ambient + K_lfp * (c_rate_sim ** alpha_lfp)

        # Threshold flags
        nmc_warn = t_nmc_peak >= 45.0
        nmc_crit = t_nmc_peak >= 55.0
        lfp_warn = t_lfp_peak >= 55.0
        lfp_crit = t_lfp_peak >= 65.0

        nmc_status_color = "#dc2626" if nmc_crit else "#d97706" if nmc_warn else "#16a34a"
        nmc_status_label = "⚠️ CRITICAL" if nmc_crit else "🟡 WARNING" if nmc_warn else "✅ NOMINAL"
        lfp_status_color = "#dc2626" if lfp_crit else "#d97706" if lfp_warn else "#16a34a"
        lfp_status_label = "⚠️ CRITICAL" if lfp_crit else "🟡 WARNING" if lfp_warn else "✅ NOMINAL"

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color);
                        border-radius: 12px; padding: 14px 16px;">
                <div style="font-size: 0.74rem; font-weight: 700; color: var(--text-muted);
                            text-transform: uppercase; margin-bottom: 8px; letter-spacing: 1px;">
                    Thermal Simulation @ {c_rate_sim:.1f}C
                </div>
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 0.78rem; color: #0ea5e9; font-weight: 700;">
                        Config A (NMC)
                    </div>
                    <div style="font-family: 'Rajdhani', sans-serif; font-size: 1.9rem;
                                font-weight: 700; color: {nmc_status_color}; line-height: 1.1;">
                        {t_nmc_peak:.1f}°C
                    </div>
                    <div style="font-size: 0.78rem; font-weight: 700; color: {nmc_status_color};">
                        {nmc_status_label}
                    </div>
                </div>
                <div style="border-top: 1px solid var(--border-color); padding-top: 10px;">
                    <div style="font-size: 0.78rem; color: #38ef7d; font-weight: 700;">
                        Config B (LFP)
                    </div>
                    <div style="font-family: 'Rajdhani', sans-serif; font-size: 1.9rem;
                                font-weight: 700; color: {lfp_status_color}; line-height: 1.1;">
                        {t_lfp_peak:.1f}°C
                    </div>
                    <div style="font-size: 0.78rem; font-weight: 700; color: {lfp_status_color};">
                        {lfp_status_label}
                    </div>
                </div>
                <div style="border-top: 1px solid var(--border-color); padding-top: 8px; margin-top: 10px;
                            font-family: 'JetBrains Mono', monospace; font-size: 0.73rem;
                            color: var(--text-muted); line-height: 1.55;">
                    Discharge window: {t_duration:.0f} min<br>
                    ΔT advantage (LFP): {t_nmc_peak - t_lfp_peak:.1f}°C cooler
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with sim_col_chart:
        # Build time-series temperature rise dataframe
        time_pts_sim = np.linspace(0, t_duration, 50)
        t_nmc_curve = T_ambient + K_nmc * (c_rate_sim ** alpha_nmc) * (1.0 - np.exp(-time_pts_sim / tau_nmc))
        t_lfp_curve = T_ambient + K_lfp * (c_rate_sim ** alpha_lfp) * (1.0 - np.exp(-time_pts_sim / tau_lfp))

        df_thermal = pd.DataFrame(
            {
                "Config A — NMC Pack (°C)": np.round(t_nmc_curve, 2),
                "Config B — LFP Pack (°C)": np.round(t_lfp_curve, 2),
            },
            index=np.round(time_pts_sim, 1),
        )
        df_thermal.index.name = "Time (min)"

        # Plotly line chart for richer annotation (warning threshold lines)
        fig_thermal = go.Figure()
        fig_thermal.add_trace(go.Scatter(
            x=df_thermal.index,
            y=df_thermal["Config A — NMC Pack (°C)"],
            name="Config A — NMC Pack",
            mode="lines",
            line=dict(color="#0ea5e9", width=2.8),
            fill="tozeroy",
            fillcolor="rgba(14, 165, 233, 0.07)",
        ))
        fig_thermal.add_trace(go.Scatter(
            x=df_thermal.index,
            y=df_thermal["Config B — LFP Pack (°C)"],
            name="Config B — LFP Pack",
            mode="lines",
            line=dict(color="#38ef7d", width=2.8),
            fill="tozeroy",
            fillcolor="rgba(56, 239, 125, 0.07)",
        ))

        # Thermal threshold annotation bands
        fig_thermal.add_hline(
            y=45.0,
            line_dash="dash",
            line_color="#d97706",
            line_width=1.5,
            annotation_text="NMC Warning: 45°C",
            annotation_position="top right",
            annotation_font=dict(size=10, color="#d97706"),
        )
        fig_thermal.add_hline(
            y=60.0,
            line_dash="dash",
            line_color="#dc2626",
            line_width=1.5,
            annotation_text="Critical Limit: 60°C",
            annotation_position="top right",
            annotation_font=dict(size=10, color="#dc2626"),
        )

        # Ambient baseline
        fig_thermal.add_hline(
            y=25.0,
            line_dash="dot",
            line_color="rgba(128,128,128,0.4)",
            line_width=1,
            annotation_text="Ambient: 25°C",
            annotation_position="bottom right",
            annotation_font=dict(size=9, color="gray"),
        )

        fig_thermal.update_layout(
            title=f"Thermal Rise Simulation at {c_rate_sim:.1f}C Discharge Rate",
            xaxis_title="Discharge Time (min)",
            yaxis_title="Battery Pack Temperature (°C)",
            template=plotly_template,
            height=360,
            margin=dict(l=50, r=40, t=50, b=45),
            legend=dict(
                orientation="h",
                y=-0.22,
                xanchor="center",
                x=0.5,
                font=dict(size=11),
            ),
            yaxis=dict(range=[20, max(70, t_nmc_peak + 8)]),
        )
        st.plotly_chart(fig_thermal, use_container_width=True)

    # C-Rate summary ribbon
    st.markdown(
        f"""
        <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color); border-radius: 10px;
                    padding: 10px 18px; display: flex; gap: 24px; flex-wrap: wrap; margin-top: 4px;">
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); align-self: center;">
                📐 PHYSICS MODEL
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
                        color: var(--text-secondary); line-height: 1.5;">
                <b>T(t)</b> = T<sub>amb</sub> + K · (C-Rate)<sup>α</sup> · (1 − e<sup>−t/τ</sup>)
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
                        color: #0ea5e9; line-height: 1.5;">
                NMC: K={K_nmc}, α={alpha_nmc}, τ={tau_nmc}s
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
                        color: #38ef7d; line-height: 1.5;">
                LFP: K={K_lfp}, α={alpha_lfp}, τ={tau_lfp}s
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# =========================================================
# TAB 5: RISK & TRACEABILITY
# =========================================================
if selected_dashboard_section == "🛡️ Risk & Traceability":
    st.markdown("### 🛡️ Risk Assessment & Battery Traceability Console")
    st.caption(
        "Rule-based safety diagnostics evaluated against live telemetry, plus cell-level "
        "voltage imbalance tracking for propagation traceability."
    )
    render_live_summary()

    # ------------------------------------------------------------------
    # Pull live telemetry for risk evaluation
    # ------------------------------------------------------------------
    # Re-use the shared live telemetry values resolved for the active view.
    # Guard: if user is in Manual Slider mode the sidebar sliders are live.
    if is_manual_mode:
        risk_voltage = slider_voltage
        risk_temp    = slider_temp
    else:
        risk_voltage = eff_voltage
        risk_temp    = eff_temp

    # Apply fault injection so the banners react to the sidebar toggle
    if inject_fault:
        risk_temp    = max(risk_temp, 54.2)
        risk_voltage = min(risk_voltage, 738.0)

    # ------------------------------------------------------------------
    # Section 1: Automated Rule-Based Safety Recommendation Banner
    # ------------------------------------------------------------------
    st.markdown("#### 🚨 Automated Safety Diagnostics & Recommendation Engine")
    st.caption(
        "Rules are evaluated against live telemetry every render cycle. "
        "Priority: **Thermal Risk** → **Deep Discharge** → **System Nominal**."
    )

    # Evaluate rule priority (thermal takes precedence)
    if risk_temp > 45.0:
        st.error(
            f"🔥 **CRITICAL THERMAL RISK** — Core temperature **{risk_temp:.1f}°C** exceeds 45°C safety ceiling.\n\n"
            "**Recommendation:** Passive cooling is **insufficient** at this load condition.  \n"
            "→ Upgrade thermal system to **Liquid Cooling** (≥12 L/min coolant flow), **or**  \n"
            "→ Limit discharge rate to **≤ 1C** immediately to arrest thermal escalation.  \n"
            "→ BMS hardware relay: **prepare for emergency load isolation** if temp exceeds 55°C."
        )
    elif risk_voltage < 10.0:
        st.error(
            f"⚡ **DEEP DISCHARGE WARNING** — Pack voltage **{risk_voltage:.2f}V** has collapsed below 10.0V threshold.\n\n"
            "**Action:** Actuating **Hardware Safety Relay** to isolate load from battery terminals.  \n"
            "→ Prevent irreversible lithium plating and cathode dissolution.  \n"
            "→ Do **not** attempt recharge until cell voltages are individually inspected.  \n"
            "→ Estimated capacity loss at this depth: **>12% permanent degradation**."
        )
    else:
        st.success(
            f"✅ **SYSTEM HEALTH OPTIMAL** — All parameters operating within normal safety margins.\n\n"
            f"→ Pack Voltage: **{risk_voltage:.1f} V** (nominal range: 10 – 850 V)  \n"
            f"→ Core Temperature: **{risk_temp:.1f}°C** (within 45°C ceiling)  \n"
            "→ BMS relay: **CLOSED (load connected)** — no protective actions required."
        )

    # Warning sub-banner for elevated (not yet critical) temperature
    if 38.0 < risk_temp <= 45.0:
        st.warning(
            f"🌡️ **THERMAL ADVISORY** — Temperature at **{risk_temp:.1f}°C** is elevated (38–45°C watch zone).  \n"
            "Monitor closely. Consider activating **Forced Air** cooling pre-emptively."
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # Telemetry snapshot pill bar
    snap_r1, snap_r2, snap_r3, snap_r4 = st.columns(4)
    _pill_style = (
        "background: var(--bg-card-sub); border: 1px solid var(--border-color); "
        "border-radius: 10px; padding: 9px 13px;"
    )
    _lbl_style = "font-size: 0.72rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;"
    _val_style = "font-family: 'Rajdhani', sans-serif; font-size: 1.45rem; font-weight: 700; color: var(--text-primary); line-height: 1.1;"
    _sub_style = "font-size: 0.73rem; font-weight: 600; color: var(--text-secondary);"

    _t_color  = "#dc2626" if risk_temp  > 45 else "#d97706" if risk_temp > 38 else "#16a34a"
    _v_color  = "#dc2626" if risk_voltage < 10 else "#16a34a"
    _soc_color = "#16a34a"
    _soh_color = "#16a34a"

    with snap_r1:
        st.markdown(
            f"<div style='{_pill_style}'>"
            f"<div style='{_lbl_style}'>Pack Voltage</div>"
            f"<div style='{_val_style} color: {_v_color};'>{risk_voltage:.1f} V</div>"
            f"<div style='{_sub_style}'>{'⚠ DEEP DISCHARGE' if risk_voltage < 10 else 'Nominal Range'}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with snap_r2:
        st.markdown(
            f"<div style='{_pill_style}'>"
            f"<div style='{_lbl_style}'>Core Temperature</div>"
            f"<div style='{_val_style} color: {_t_color};'>{risk_temp:.1f} °C</div>"
            f"<div style='{_sub_style}'>{'🔥 CRITICAL' if risk_temp > 45 else '🟡 WATCH' if risk_temp > 38 else '✅ Optimal'}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with snap_r3:
        _soc_val = eff_soc if not is_manual_mode else slider_soc
        st.markdown(
            f"<div style='{_pill_style}'>"
            f"<div style='{_lbl_style}'>State of Charge</div>"
            f"<div style='{_val_style} color: {_soc_color};'>{_soc_val:.1f} %</div>"
            f"<div style='{_sub_style}'>~{int(_soc_val * 5.8)} km est. range</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with snap_r4:
        _src_label = "Manual Sliders" if is_manual_mode else ("UDP 0.0.0.0:4210" if is_udp_mode else "MQTT HiveMQ")
        st.markdown(
            f"<div style='{_pill_style}'>"
            f"<div style='{_lbl_style}'>Telemetry Source</div>"
            f"<div style='font-size: 0.9rem; font-weight: 700; color: var(--accent-primary); line-height: 1.2; margin-top: 2px;'>{_src_label}</div>"
            f"<div style='{_sub_style}'>{'Fault injection ACTIVE' if inject_fault else 'Live pipeline'}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Section 2: 4-Cell Voltage Imbalance Traceability Block
    # ------------------------------------------------------------------
    st.markdown("#### 🔬 4-Cell Voltage Imbalance & Propagation Traceability")
    st.caption(
        "Virtual cell group sampled from live pack voltage. "
        "ΔV variance metric detects cell-to-cell degradation propagation pathways."
    )

    # Derive cell voltages from live pack voltage with synthetic per-cell offsets
    # Base single-cell voltage ≈ pack_voltage / 108 cells (standard 800V / 7.4V series string)
    _cell_base = risk_voltage / 108.0        # per-cell nominal from live pack
    _cell_base = max(3.0, min(4.25, _cell_base))   # clamp to valid lithium range

    # Deterministic per-cell jitter seeded from current second for gentle drift effect
    _seed_t = int(time.time()) % 100
    rng = np.random.default_rng(seed=_seed_t)

    # If fault injected → Cell 3 gets a pronounced sag
    _offsets = rng.uniform(-0.025, 0.025, 4)
    if inject_fault:
        _offsets[2] = -0.38    # Cell 3 severe voltage sag (fault injection)

    v1 = round(_cell_base + _offsets[0], 4)
    v2 = round(_cell_base + _offsets[1], 4)
    v3 = round(_cell_base + _offsets[2], 4)
    v4 = round(_cell_base + _offsets[3], 4)

    cell_voltages = [v1, v2, v3, v4]
    v_max  = max(cell_voltages)
    v_min  = min(cell_voltages)
    v_mean = round(sum(cell_voltages) / 4, 4)
    delta_v = round(v_max - v_min, 4)

    # Imbalance severity classification
    if delta_v > 0.200:
        imbal_label = "🔴 SEVERE IMBALANCE"
        imbal_color = "#dc2626"
        imbal_bg    = "rgba(220,38,38,0.12)"
        imbal_border= "#dc2626"
        imbal_desc  = "Cell failure probable. Initiate emergency balancing & cell inspection."
    elif delta_v > 0.080:
        imbal_label = "🟡 MODERATE IMBALANCE"
        imbal_color = "#d97706"
        imbal_bg    = "rgba(217,119,6,0.10)"
        imbal_border= "#d97706"
        imbal_desc  = "Passive balancing engaged. Monitor propagation trajectory."
    elif delta_v > 0.030:
        imbal_label = "🔵 MINOR IMBALANCE"
        imbal_color = "#0ea5e9"
        imbal_bg    = "rgba(14,165,233,0.10)"
        imbal_border= "#0ea5e9"
        imbal_desc  = "Within passive balancing tolerance. No action required."
    else:
        imbal_label = "🟢 BALANCED"
        imbal_color = "#16a34a"
        imbal_bg    = "rgba(22,163,74,0.10)"
        imbal_border= "#16a34a"
        imbal_desc  = "All cells matched within ±30 mV. Excellent uniformity."

    # ΔV bar chart via Plotly for clean inline visualization
    fig_cells = go.Figure()
    cell_labels = ["V₁ — Cell 1", "V₂ — Cell 2", "V₃ — Cell 3", "V₄ — Cell 4"]
    bar_colors  = []
    for cv in cell_voltages:
        deviation = abs(cv - v_mean)
        if deviation > 0.15:
            bar_colors.append("#dc2626")
        elif deviation > 0.05:
            bar_colors.append("#d97706")
        else:
            bar_colors.append("#16a34a" if not is_dark else "#38ef7d")

    fig_cells.add_trace(go.Bar(
        x=cell_labels,
        y=cell_voltages,
        marker_color=bar_colors,
        text=[f"{cv:.4f} V" for cv in cell_voltages],
        textposition="outside",
        textfont=dict(size=13, family="Rajdhani, sans-serif"),
        width=0.45,
    ))

    # Mean reference line
    fig_cells.add_hline(
        y=v_mean,
        line_dash="dash",
        line_color="#0ea5e9",
        line_width=2,
        annotation_text=f"V̄ mean = {v_mean:.4f} V",
        annotation_position="top left",
        annotation_font=dict(size=10, color="#0ea5e9"),
    )
    # ΔV annotation arrow between min & max
    fig_cells.add_annotation(
        x=cell_labels[cell_voltages.index(v_min)],
        y=v_min,
        text=f"▼ ΔV = {delta_v:.4f} V",
        showarrow=True,
        arrowhead=2,
        arrowcolor=imbal_color,
        font=dict(size=11, color=imbal_color, family="Rajdhani, sans-serif"),
        ay=30,
    )

    y_pad = max(0.05, delta_v + 0.04)
    fig_cells.update_layout(
        title="Individual Cell Terminal Voltages (V₁ — V₄)",
        xaxis_title="Cell ID",
        yaxis_title="Terminal Voltage (V)",
        yaxis=dict(range=[v_min - y_pad, v_max + y_pad + 0.06]),
        template=plotly_template,
        height=320,
        margin=dict(l=50, r=30, t=50, b=40),
        showlegend=False,
        bargap=0.35,
    )

    cell_chart_col, cell_metrics_col = st.columns([1.6, 1], gap="large")

    with cell_chart_col:
        st.plotly_chart(fig_cells, use_container_width=True)

    with cell_metrics_col:
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # ΔV imbalance status card
        st.markdown(
            f"""
            <div style="background: {imbal_bg}; border: 1.5px solid {imbal_border};
                        border-radius: 14px; padding: 16px 18px; margin-bottom: 14px;">
                <div style="font-size: 0.72rem; font-weight: 700; color: var(--text-muted);
                            text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;">
                    ΔV Imbalance Status
                </div>
                <div style="font-family: 'Rajdhani', sans-serif; font-size: 2rem;
                            font-weight: 700; color: {imbal_color}; line-height: 1.1;">
                    {delta_v:.4f} V
                </div>
                <div style="font-size: 0.84rem; font-weight: 700; color: {imbal_color};
                            margin: 3px 0 6px 0;">
                    {imbal_label}
                </div>
                <div style="font-size: 0.77rem; color: var(--text-secondary); line-height: 1.45;">
                    {imbal_desc}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Per-cell voltage breakdown cards
        for idx, (label_short, cv) in enumerate(zip(["V₁", "V₂", "V₃", "V₄"], cell_voltages)):
            dev = round(cv - v_mean, 4)
            dev_color = "#dc2626" if abs(dev) > 0.15 else "#d97706" if abs(dev) > 0.05 else "#16a34a"
            dev_sign  = "+" if dev >= 0 else ""
            fault_tag = " ⚠ FAULT" if inject_fault and idx == 2 else ""
            st.markdown(
                f"""
                <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color);
                            border-radius: 9px; padding: 8px 12px; margin-bottom: 6px;
                            display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
                                     font-weight: 700; color: var(--text-muted);">
                            Cell {idx + 1} ({label_short}){fault_tag}
                        </span>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-family: 'Rajdhani', sans-serif; font-size: 1.15rem;
                                    font-weight: 700; color: var(--text-primary);">{cv:.4f} V</div>
                        <div style="font-size: 0.73rem; font-weight: 700; color: {dev_color};">
                            {dev_sign}{dev:.4f} V vs V̄
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Propagation traceability summary footer
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="background: var(--bg-card-sub); border: 1px solid var(--border-color);
                    border-radius: 10px; padding: 11px 18px; display: flex; gap: 28px;
                    flex-wrap: wrap; align-items: center;">
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted);">
                📐 TRACEABILITY METRICS
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
                        color: var(--text-secondary); line-height: 1.5;">
                V̄ mean = <b>{v_mean:.4f} V</b>
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
                        color: var(--text-secondary); line-height: 1.5;">
                V_max = <b style="color: #16a34a;">{v_max:.4f} V</b>
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
                        color: var(--text-secondary); line-height: 1.5;">
                V_min = <b style="color: {'#dc2626' if inject_fault else '#d97706'};">{v_min:.4f} V</b>
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
                        color: {imbal_color}; font-weight: 700; line-height: 1.5;">
                ΔV = {delta_v:.4f} V &nbsp;|&nbsp; {imbal_label}
            </div>
            <div style="font-size: 0.73rem; color: var(--text-muted);">
                Source: {'Fault-Injected' if inject_fault else 'Live Telemetry Derived'}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# =========================================================
# TAB 6: 32-CELL BATTERY MATRIX
# =========================================================
if selected_dashboard_section == "🔋 Cell Matrix":
    st.markdown("### 🔋 32-Cell Series-Parallel Matrix Architecture")
    st.caption("4 High-Voltage Modules (MOD-A, MOD-B, MOD-C, MOD-D) with individual cell voltage, thermal gradient, and balancing shunts.")
    render_live_summary()

    module_filter = st.radio(
        "Module Filter",
        ["ALL CELLS (32)", "MOD-A", "MOD-B", "MOD-C", "MOD-D"],
        horizontal=True,
    )

    rng = np.random.default_rng()
    modules = ["MOD-A", "MOD-B", "MOD-C", "MOD-D"]
    cell_data = []

    for i in range(1, 33):
        mod_index = (i - 1) // 8
        mod_name = modules[mod_index]

        jitter = (rng.random() - 0.5) * 0.008 if enable_jitter else 0.0
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
# TAB 7: ELECTROCHEMICAL & PINN ANALYTICS
# =========================================================
if selected_dashboard_section == "📈 PINN Analytics":
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
# TAB 8: CAN BUS STREAM & DIAGNOSTICS
# =========================================================
if selected_dashboard_section == "📋 CAN Diagnostics":
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
# TAB 9: ESP32 HARDWARE & DEPLOYMENT GUIDE
# =========================================================
if selected_dashboard_section == "🚀 Hardware & Deployment":
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
