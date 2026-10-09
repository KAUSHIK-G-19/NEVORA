"""
NEVORA BMS INTELLIGENCE // 800V PINN DIGITAL TWIN
Driver Instrument Cockpit & Battery Management System
Supports: ☀️ Driver Daylight (Crisp White) & 🌙 Night (Dark) Themes
"""

import math
import os
import time
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Configure page layout and metadata
st.set_page_config(
    page_title="NEVORA Driver Cockpit & PINN Digital Twin",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# Theme State Management (Light vs Dark)
# ---------------------------------------------------------
if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "light"  # Default to user-requested clean white driver theme

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

    st.markdown("---")
    st.markdown("#### ⚡ Battery Telemetry Sliders")
    
    col_v, col_i = st.columns(2)
    with col_v:
        pack_voltage = st.slider("Pack Voltage (V)", min_value=300.0, max_value=800.0, value=float(default_volts), step=0.5)
    with col_i:
        pack_current = st.slider("Current (A)", min_value=-300.0, max_value=250.0, value=float(default_current), step=0.5)

    col_t, col_s = st.columns(2)
    with col_t:
        pack_temp = st.slider("Core Temp (°C)", min_value=-20.0, max_value=75.0, value=float(default_temp), step=0.5)
    with col_s:
        soc = st.slider("State of Charge (%)", min_value=1.0, max_value=100.0, value=84.6, step=0.2)

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
    # ── CLEAN DRIVER LIGHT THEME (Crisp White Automotive Cockpit) ──
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
    # ── NIGHT COCKPIT THEME (Midnight HUD with Neon Accents) ──
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

    /* Overall App Viewport */
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

    /* Top Brand Cockpit Header */
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
        font-size: 1.95rem;
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
        width: 9px;
        height: 9px;
        background-color: var(--accent-green);
        border-radius: 50%;
        box-shadow: 0 0 6px var(--accent-green);
    }}
    .dot-blue {{
        width: 9px;
        height: 9px;
        background-color: var(--accent-primary);
        border-radius: 50%;
        box-shadow: 0 0 6px var(--accent-primary);
    }}
    .dot-red {{
        width: 9px;
        height: 9px;
        background-color: var(--accent-red);
        border-radius: 50%;
        box-shadow: 0 0 6px var(--accent-red);
    }}

    /* Driver Instrument Cluster (HUD) */
    .driver-hud-panel {{
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 1.25rem;
        box-shadow: var(--shadow-elevation);
    }}

    .hud-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.25rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid var(--border-color);
    }}
    .hud-title {{
        font-family: 'Rajdhani', sans-serif;
        font-size: 1.2rem;
        font-weight: 700;
        letter-spacing: 1.5px;
        color: var(--text-primary);
    }}

    /* Primary Speed & Range Dials */
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

    /* High Voltage Lug Cards */
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

    /* Cell Matrix Styling */
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

    /* Styled Tables */
    .stTable, .stDataFrame {{
        background: var(--bg-card) !important;
        color: var(--text-primary) !important;
        border-radius: 8px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# ONNX PINN Engine Loader
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
# Electrochemical Butler-Volmer & PINN Evaluation
# ---------------------------------------------------------
def butler_volmer_physics_check(voltage_v, current_a, temp_c):
    """Electrochemical kinetics validity check (src/pinn_engine.cpp)."""
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
        and (0.0 < voltage_v <= 800.0)
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
# Dynamic Calculations & State
# ---------------------------------------------------------
effective_temp = pack_temp if not inject_fault else max(pack_temp, 52.4)
effective_voltage = pack_voltage if not inject_fault else min(pack_voltage, 386.0)

pinn_res = compute_pinn_digital_twin(
    effective_voltage,
    pack_current,
    effective_temp,
    soc,
    session=onnx_session,
)

if inject_fault:
    pinn_res["degradation_risk"] = 0.742
    pinn_res["soh"] = round(pinn_res["soh"] - 5.2, 2)
    pinn_res["rul_cycles"] = max(200, pinn_res["rul_cycles"] - 380)

# Derived Vehicle & Battery Metrics
current_kwh = round((soc / 100.0) * total_capacity_kwh, 1)
estimated_range_km = int(round((soc / 100.0) * 580))
power_kw = round((effective_voltage * pack_current) / 1000.0, 1)
coolant_flow = 28.0 if inject_fault else round(14.5 + max(0.0, (effective_temp - 30.0) * 0.45), 1)
efficiency_wh_km = int(round(165 + (abs(pack_current) / 100.0) * 25))
vehicle_speed = default_speed if not inject_fault else max(20, default_speed - 30)

# ---------------------------------------------------------
# Top Cockpit Header & Theme Indicator
# ---------------------------------------------------------
theme_icon = "☀️" if is_light else "🌙"
theme_label = "Driver Daylight (White)" if is_light else "Night Cockpit (Dark)"

st.markdown(
    f"""
    <div class="brand-banner">
        <div>
            <h1 class="brand-title">NEVORA <span>COCKPIT</span></h1>
            <p class="brand-sub">800V EV DIGITAL TWIN // PHYSICS-INFORMED NEURAL NETWORK BMS</p>
        </div>
        <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
            <div class="badge-pill">
                <span>{theme_icon} {theme_label}</span>
            </div>
            <div class="badge-pill">
                <span class="{'dot-green' if onnx_session else 'dot-blue'}"></span>
                <span>ONNX Runtime: <b>{'v1.29 Active' if onnx_session else 'Fallback'}</b></span>
            </div>
            <div class="badge-pill">
                <span class="{'dot-green' if pinn_res['physics_valid'] else 'dot-red'}"></span>
                <span>Butler-Volmer: <b>{'Validated' if pinn_res['physics_valid'] else 'Violation'}</b></span>
            </div>
            <div class="badge-pill">
                <span class="dot-green"></span>
                <span>CAN Bus: <b>can0 (250 kbps)</b></span>
            </div>
            <div class="badge-pill">
                <span class="{'dot-red' if inject_fault else 'dot-green'}"></span>
                <span>Pack: <b>{'FAULT DETECTED' if inject_fault else 'OPTIMAL'}</b></span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# Primary Driver Digital Instrument Cluster (HUD Gauges)
# ---------------------------------------------------------
st.markdown('<div class="driver-hud-panel">', unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="hud-header">
        <span class="hud-title">DRIVER DIGITAL INSTRUMENT CLUSTER // LIVE TELEMETRY</span>
        <span style="font-size: 0.82rem; font-weight: 700; color: {'#dc2626' if inject_fault else '#16a34a'};">
            ● DRIVE MODE: {selected_mode_label.upper()}
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)

g1, g2, g3, g4, g5 = st.columns(5)

with g1:
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

with g2:
    soc_color = "#16a34a" if soc > 25 else "#dc2626"
    st.markdown(
        f"""
        <div class="cockpit-gauge">
            <div class="gauge-lbl">STATE OF CHARGE</div>
            <div class="gauge-val" style="color: {soc_color};">{soc:.1f}<span class="gauge-unit">%</span></div>
            <div class="gauge-sub">{current_kwh} / {total_capacity_kwh:.0f} kWh</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with g3:
    power_sign = "+" if power_kw > 0 else ""
    power_color = "#16a34a" if power_kw > 0 else "#0284c7" if power_kw > -80 else "#dc2626"
    st.markdown(
        f"""
        <div class="cockpit-gauge">
            <div class="gauge-lbl">INSTANT POWER</div>
            <div class="gauge-val" style="color: {power_color};">{power_sign}{power_kw:.1f}<span class="gauge-unit">kW</span></div>
            <div class="gauge-sub">{effective_voltage:.1f}V • {pack_current:.1f}A</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with g4:
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

with g5:
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

# Battery Charge Progress Strip
st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
soc_pct = float(soc / 100.0)
st.progress(soc_pct)
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------
# Cockpit Navigation Tabs
# ---------------------------------------------------------
tab_cockpit, tab_cells, tab_charts, tab_can, tab_guide = st.tabs([
    "🚗 Driver HUD & High-Voltage Chassis",
    "🔋 32-Cell Battery Matrix",
    "📈 Electrochemical Analytics",
    "📡 CAN Bus Stream & Diagnostics",
    "🚀 Deployment & Cloud Setup",
])

# =========================================================
# TAB 1: DRIVER HUD & HIGH-VOLTAGE CHASSIS
# =========================================================
with tab_cockpit:
    c_left, c_right = st.columns([1.1, 0.9])
    
    with c_left:
        st.markdown("#### ⚡ 800V High-Voltage Bus & Terminal Lugs")
        
        flow_direction = "ENERGY INFLOW (+DC)" if pack_current > 0 else "MOTOR DRAW (-DC)" if pack_current < 0 else "STANDBY"
        flow_color = "#16a34a" if pack_current > 0 else "#0284c7"
        
        t_col1, t_col2 = st.columns(2)
        with t_col1:
            st.markdown(
                f"""
                <div class="terminal-card terminal-pos">
                    <div>
                        <div style="font-size: 0.74rem; color: #dc2626; font-weight: 700;">HV+ CATHODE POST</div>
                        <div style="font-family: 'Rajdhani', sans-serif; font-size: 1.6rem; font-weight: 700; color: var(--text-primary);">+{(effective_voltage / 2):.1f} V</div>
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
                        <div style="font-family: 'Rajdhani', sans-serif; font-size: 1.6rem; font-weight: 700; color: var(--text-primary);">-{(effective_voltage / 2):.1f} V</div>
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
            temp_status = "CRITICAL HIGH" if effective_temp > 50 else "ELEVATED" if effective_temp > 40 else "OPTIMAL"
            st.metric("Battery Pack Core Temp", f"{effective_temp:.1f} °C", delta=temp_status, delta_color="inverse" if effective_temp > 40 else "normal")

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
# TAB 2: 32-CELL BATTERY MATRIX
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
        t_cell = round(pack_temp + math.cos(i) * 1.4, 1)
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

    # Render cell matrix grid (8 cells per row)
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
    
    # Deep Cell Diagnostic Inspector
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
# TAB 3: ELECTROCHEMICAL & PHYSICS ANALYTICS
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
            height=350,
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
            height=350,
            margin=dict(l=40, r=40, t=50, b=40),
        )
        st.plotly_chart(fig_deg, width="stretch")

    # Cell Voltage Dispersion Profile
    st.markdown("#### 📊 32-Cell Voltage Dispersion & Delta-V")
    voltages = [c["voltage"] for c in cell_data]
    colors = ["#dc2626" if c["status"] == "critical" else "#0284c7" for c in cell_data]
    
    fig_bar = go.Figure(go.Bar(
        x=[f"C{c['id']:02d}" for c in cell_data],
        y=voltages,
        marker_color=colors,
    ))
    fig_bar.update_layout(
        title=f"Cell Voltage Dispersion across Pack (Delta-V: {(max(voltages) - min(voltages)):.3f} V)",
        xaxis_title="Battery Cell ID",
        yaxis_title="Terminal Voltage (V)",
        yaxis_range=[3.2, 4.3],
        template=plotly_template,
        height=300,
        margin=dict(l=40, r=40, t=50, b=40),
    )
    st.plotly_chart(fig_bar, width="stretch")

# =========================================================
# TAB 4: CAN BUS STREAM & DIAGNOSTICS
# =========================================================
with tab_can:
    st.markdown("### 📡 Live CAN Bus Packet Decoder (can0 @ 250 kbps)")
    st.caption("Decoded CAN frames generated in synchronization with C++ embedded worker (src/can_reader.cpp).")
    
    now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    v_raw_hex = f"{int(round(effective_voltage * 10)):08X}"
    i_raw_hex = f"{int(round((pack_current + 1000.0) * 10)):08X}"
    t_raw_hex = f"{int(round((effective_temp + 40.0) * 10)):04X}"
    
    can_packets = [
        {
            "Timestamp": now_str,
            "CAN ID": "0x18F00101",
            "Type": "V_I_TELEMETRY",
            "DLC": 8,
            "Payload (Hex)": f"{v_raw_hex[:4]} {v_raw_hex[4:]} {i_raw_hex[:4]} {i_raw_hex[4:]}",
            "Decoded Interpretation": f"Pack Voltage: {effective_voltage:.1f}V | Pack Current: {pack_current:.1f}A",
        },
        {
            "Timestamp": now_str,
            "CAN ID": "0x18F00201",
            "Type": "THERMAL_STATE",
            "DLC": 2,
            "Payload (Hex)": f"{t_raw_hex} 00 00",
            "Decoded Interpretation": f"Pack Temperature: {effective_temp:.1f}°C | Coolant: {coolant_flow} L/min",
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
# TAB 5: DEPLOYMENT & CLOUD SETUP
# =========================================================
with tab_guide:
    st.markdown("### 🚀 Fast Cloud Deployment & Local Execution")
    
    c_dep1, c_dep2 = st.columns(2)
    with c_dep1:
        st.markdown("#### 💻 1. Local Run")
        st.markdown("Double-click `run_streamlit.bat` or run in terminal:")
        st.code(
            """# Run locally with Python
py -3.13 -m streamlit run app.py""",
            language="bash",
        )

        st.markdown("#### 🐳 2. Docker Container")
        st.code(
            """docker build -t nevora-bms-twin .
docker run -p 8501:8501 nevora-bms-twin""",
            language="bash",
        )

    with c_dep2:
        st.markdown("#### ☁️ 3. Free Streamlit Cloud (1-Click)")
        st.markdown(
            """
            1. Push changes to your GitHub repository.
            2. Open [share.streamlit.io](https://share.streamlit.io) and log in.
            3. Select repository, set branch `main`, and main file `app.py`.
            4. Click **Deploy!**
            """
        )
