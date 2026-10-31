"""
NEVORA EV Battery Digital Twin — Standalone 4-Tab HIL Dashboard
================================================================
Tabs:
  1. 🔴 Live Hardware HIL Telemetry  — Background UDP thread (port 4210)
  2. ⚡  Pack Configurator            — Cell-chemistry S/P sizing engine
  3. 📊  Multi-Physics Trade-Offs     — Radar chart + C-Rate thermal sim
  4. 🛡️  Risk & Traceability          — Rule-based banners + ΔV imbalance

Run:  py -m streamlit run nevora_hil_dashboard.py
"""

# ── stdlib ─────────────────────────────────────────────────────────────────
import collections
import json
import math
import socket
import threading
import time
from datetime import datetime

# ── third-party ────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ═══════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="NEVORA HIL Digital Twin",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Page title (visible in all tabs) ───────────────────────────────────────
st.title("NEVORA: EV Battery Digital Twin & Design Platform")

# ═══════════════════════════════════════════════════════════════════════════
# DARK-THEME CSS INJECTION
# ═══════════════════════════════════════════════════════════════════════════
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800
        &family=Rajdhani:wght@500;600;700
        &family=JetBrains+Mono:wght@400;600;700&display=swap');

    :root {
        --bg-main:       #070b14;
        --bg-card:       rgba(15, 23, 42, 0.90);
        --bg-card-sub:   rgba(30, 41, 59, 0.65);
        --text-primary:  #f1f5f9;
        --text-secondary:#cbd5e1;
        --text-muted:    #94a3b8;
        --border:        rgba(255,255,255,0.09);
        --border-accent: rgba(0,242,254,0.40);
        --shadow:        0 8px 32px rgba(0,0,0,0.55);
        --cyan:          #00f2fe;
        --green:         #38ef7d;
        --amber:         #fbbf24;
        --red:           #ef4444;
        --blue:          #38bdf8;
    }

    .stApp {
        background-color: var(--bg-main) !important;
        color: var(--text-primary) !important;
        font-family: 'Manrope', sans-serif !important;
    }
    header[data-testid="stHeader"]  { background: transparent !important; }
    div[data-testid="stSidebar"]    { background: var(--bg-card) !important; }
    .block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; }
    code, pre { font-family: 'JetBrains Mono', monospace !important; }

    /* ── brand banner ── */
    .nv-banner {
        background: linear-gradient(135deg, rgba(15,23,42,.98), rgba(8,15,30,.99));
        border: 1px solid var(--border-accent);
        border-radius: 16px;
        padding: 1.1rem 1.6rem;
        margin-bottom: 1.1rem;
        box-shadow: var(--shadow);
        display: flex; justify-content: space-between;
        align-items: center; flex-wrap: wrap; gap: .8rem;
    }
    .nv-title {
        margin: 0;
        font-family: 'Rajdhani', sans-serif;
        font-size: 2rem; font-weight: 700;
        letter-spacing: 2px; color: var(--text-primary);
    }
    .nv-title span { color: var(--cyan); }
    .nv-sub {
        margin: 0; font-size: .78rem;
        color: var(--text-muted); letter-spacing: 1px; font-weight: 600;
    }

    /* ── pill badge ── */
    .pill {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 5px 13px;
        background: var(--bg-card-sub);
        border: 1px solid var(--border);
        border-radius: 30px; font-size: .78rem;
        font-weight: 600; color: var(--text-primary);
    }
    .dot { width:9px; height:9px; border-radius:50%; }
    .dot-g { background:var(--green);  box-shadow:0 0 7px var(--green);
              animation:pulse 1.5s infinite; }
    .dot-r { background:var(--red);    box-shadow:0 0 7px var(--red); }
    .dot-a { background:var(--amber);  box-shadow:0 0 7px var(--amber); }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

    /* ── cockpit gauge card ── */
    .cg {
        background: var(--bg-card-sub);
        border: 1px solid var(--border);
        border-radius: 14px; padding: 1.1rem .9rem;
        text-align: center; transition: .2s;
    }
    .cg:hover { border-color: var(--border-accent); transform: translateY(-2px); }
    .cg-lbl { font-size:.72rem; font-weight:700; letter-spacing:1.2px;
               color:var(--text-muted); text-transform:uppercase; margin-bottom:.3rem; }
    .cg-val { font-family:'Rajdhani',sans-serif; font-size:2.6rem;
               font-weight:700; line-height:1; color:var(--text-primary); }
    .cg-unit{ font-size:1rem; font-weight:600; color:var(--cyan); margin-left:3px; }
    .cg-sub { font-size:.74rem; font-weight:600; color:var(--text-secondary);
               margin-top:.3rem; }

    /* ── info tile ── */
    .tile {
        background: var(--bg-card-sub);
        border: 1px solid var(--border);
        border-radius: 10px; padding: 9px 13px;
    }
    .tile-lbl { font-size:.71rem; font-weight:700; color:var(--text-muted);
                text-transform:uppercase; }
    .tile-val { font-family:'Rajdhani',sans-serif; font-size:1.35rem;
                font-weight:700; color:var(--text-primary); line-height:1.15; }
    .tile-sub { font-size:.72rem; font-weight:600; color:var(--text-secondary); }

    /* ── relay badge ── */
    .relay-ok  { color:var(--green); font-weight:700; }
    .relay-off { color:var(--red);   font-weight:700; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. BACKGROUND UDP TELEMETRY MANAGER  (port 4210)
# ═══════════════════════════════════════════════════════════════════════════
class UdpManager:
    """Thread-safe singleton: receives ESP32 JSON packets on UDP :4210."""

    _DEFAULT = dict(
        packVoltage=792.40, packCurrent=-34.80,
        cellTemp=31.20, SoC=82.50, SoH=98.40,
    )

    def __init__(self, ip="0.0.0.0", port=4210):
        self.ip, self.port = ip, port
        self._lock       = threading.Lock()
        self.connected   = False
        self.packet_count = 0
        self.last_sender = "—"
        self._data       = dict(self._DEFAULT, timestamp=time.time(),
                                source="Awaiting ESP32")
        self._history    = collections.deque(maxlen=60)

        # Pre-populate history with sinusoidal seed data
        now = time.time()
        for k in range(20):
            t0 = now - (20 - k) * 0.5
            self._history.append(dict(
                time=datetime.fromtimestamp(t0).strftime("%H:%M:%S"),
                timestamp=t0,
                packVoltage=792.4 + math.sin(k * .4) * 1.5,
                packCurrent=-34.8 + math.cos(k * .4) * 8.0,
                cellTemp=31.2 + k * .02,
                SoC=82.5 - k * .01,
            ))

        threading.Thread(target=self._worker, daemon=True).start()

    # ── internal UDP receive loop ─────────────────────────────────────────
    def _worker(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.ip, self.port))
            sock.settimeout(1.0)
            self.connected = True
        except OSError as exc:
            print(f"[UDP] Bind error on {self.ip}:{self.port}: {exc}")
            return

        while True:
            try:
                raw, addr = sock.recvfrom(1024)
                pkt = json.loads(raw.decode("utf-8", errors="ignore"))
                d = self._DEFAULT
                v   = float(pkt.get("v",   pkt.get("packVoltage",  d["packVoltage"])))
                i   = float(pkt.get("i",   pkt.get("packCurrent",  d["packCurrent"])))
                t   = float(pkt.get("t",   pkt.get("cellTemp",     d["cellTemp"])))
                soc = float(pkt.get("soc", pkt.get("SoC",          d["SoC"])))
                soh = float(pkt.get("soh", pkt.get("SoH",          d["SoH"])))
                now = time.time()
                with self._lock:
                    self.packet_count += 1
                    self.last_sender   = f"{addr[0]}:{addr[1]}"
                    self._data = dict(
                        packVoltage=v, packCurrent=i, cellTemp=t,
                        SoC=soc, SoH=soh,
                        timestamp=now,
                        source=f"UDP ESP32 ({self.last_sender})",
                    )
                    self._history.append(dict(
                        time=datetime.fromtimestamp(now).strftime("%H:%M:%S"),
                        timestamp=now,
                        packVoltage=v, packCurrent=i, cellTemp=t, SoC=soc,
                    ))
            except socket.timeout:
                continue
            except Exception:
                continue

    # ── public API ────────────────────────────────────────────────────────
    def push_mock(self, v, i, t, soc, soh):
        """Inject a synthetic packet (used by in-app mock toggle)."""
        now = time.time()
        with self._lock:
            self.packet_count += 1
            self.last_sender   = "127.0.0.1 (Mock)"
            self._data = dict(
                packVoltage=round(v, 2), packCurrent=round(i, 2),
                cellTemp=round(t, 2), SoC=round(soc, 2), SoH=round(soh, 2),
                timestamp=now, source="In-Dashboard Mock",
            )
            self._history.append(dict(
                time=datetime.fromtimestamp(now).strftime("%H:%M:%S"),
                timestamp=now,
                packVoltage=round(v, 2), packCurrent=round(i, 2),
                cellTemp=round(t, 2), SoC=round(soc, 2),
            ))

    def snapshot(self):
        with self._lock:
            return dict(self._data), list(self._history), self.packet_count


@st.cache_resource
def get_udp():
    return UdpManager()


udp = get_udp()

# ═══════════════════════════════════════════════════════════════════════════
# 2. SIDEBAR — mock stream toggle + fault injection
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ NEVORA Dashboard Controls")
    mock_on = st.toggle("🧪 Run In-App Mock Stream", value=False,
                        help="Generates synthetic 500 ms packets into the UDP pipeline.")
    if mock_on:
        _t = time.time()
        udp.push_mock(
            v   = 792.0 + math.sin(_t * 1.5) * 6.0,
            i   = -34.0 + math.sin(_t * .9) * 28.0,
            t   = 31.0  + abs(math.sin(_t * .9) * 28.0) / 50.0 * 1.2,
            soc = max(10.0, 84.5 - (_t % 300) / 300 * 5.0),
            soh = 98.40,
        )

    st.markdown("---")
    inject_fault = st.toggle(
        "⚠️ Inject Thermal / V-Sag Fault",
        value=False,
        help="Simulates Cell #3 at 54.2°C & −380 mV sag for risk demo.",
    )
    if inject_fault:
        st.error("BMS: Cell #3 surge 54.2°C · 3.38 V detected!")

    st.markdown("---")
    st.caption("NEVORA PINN BMS v2.0 · 800V Architecture")

# ═══════════════════════════════════════════════════════════════════════════
# 3. BRAND HEADER
# ═══════════════════════════════════════════════════════════════════════════
_data, _hist, _pkts = udp.snapshot()
_udp_ok = _data.get("source", "").startswith("UDP ESP32")

st.markdown(
    f"""
    <div class="nv-banner">
        <div>
            <h1 class="nv-title">NEVORA <span>HIL COCKPIT</span></h1>
            <p class="nv-sub">EV BATTERY DIGITAL TWIN · REAL-TIME UDP HIL TELEMETRY · PORT 4210</p>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            <div class="pill">
                <span class="dot {'dot-g' if udp.connected else 'dot-r'}"></span>
                <span>UDP :4210 — <b>{'Listening' if udp.connected else 'Bind Error'}</b></span>
            </div>
            <div class="pill">
                <span class="dot {'dot-g' if _udp_ok else 'dot-a'}"></span>
                <span>Stream — <b>{'ESP32 Active' if _udp_ok else 'Awaiting'}</b></span>
            </div>
            <div class="pill">
                <span>📦 Packets: <b>{_pkts}</b></span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════════════════════════
# 4. TAB NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════
tab_hil, tab_cfg, tab_trd, tab_rsk = st.tabs([
    "🔴 Live Hardware HIL Telemetry",
    "⚡ Pack Configurator",
    "📊 Multi-Physics Trade-Offs",
    "🛡️ Risk & Traceability",
])

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TAB 1 — LIVE HARDWARE HIL TELEMETRY                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝
with tab_hil:
    st.markdown("### 🔴 Real-Time HIL Telemetry — UDP Port 4210")
    st.caption(
        "Background thread listens on `0.0.0.0:4210` for ESP32 JSON packets "
        "`{\"v\": V, \"i\": I, \"t\": T, \"soc\": S, \"soh\": H}`. "
        "Refresh page or enable Mock Stream to update."
    )

    # ── live snapshot ────────────────────────────────────────────────────
    telemetry, history, pkt_count = udp.snapshot()
    v_live   = telemetry["packVoltage"]
    i_live   = telemetry["packCurrent"]
    t_live   = telemetry["cellTemp"]
    soc_live = telemetry["SoC"]
    soh_live = telemetry["SoH"]

    if inject_fault:
        t_live   = max(t_live,  54.2)
        v_live   = min(v_live, 738.0)

    # Derived
    relay_ok   = v_live >= 10.0 and t_live <= 55.0
    power_kw   = round(v_live * i_live / 1000.0, 2)
    range_km   = int(soc_live * 5.8)

    # ── status header row ─────────────────────────────────────────────────
    sh1, sh2, sh3, sh4 = st.columns(4)
    def _status_pill(col, label, value, sub, color):
        col.markdown(
            f"<div class='tile'>"
            f"<div class='tile-lbl'>{label}</div>"
            f"<div class='tile-val' style='color:{color};'>{value}</div>"
            f"<div class='tile-sub'>{sub}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    _status_pill(sh1, "UDP SOCKET",
                 "BOUND & ACTIVE" if udp.connected else "BIND ERROR",
                 f"0.0.0.0:{udp.port}",
                 "var(--green)" if udp.connected else "var(--red)")
    _status_pill(sh2, "LAST SENDER",
                 udp.last_sender,
                 f"{pkt_count} packets total",
                 "var(--cyan)")
    _status_pill(sh3, "HV RELAY",
                 "CLOSED ✔" if relay_ok else "OPEN — ISOLATED ✖",
                 "Load connected" if relay_ok else "Safety relay tripped",
                 "var(--green)" if relay_ok else "var(--red)")
    _status_pill(sh4, "DATA SOURCE",
                 telemetry.get("source", "—")[:30],
                 datetime.fromtimestamp(telemetry["timestamp"]).strftime("%H:%M:%S.%f")[:-3],
                 "var(--text-secondary)")

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # ── Plotly gauge factory ──────────────────────────────────────────────
    def _gauge(title, val, lo, hi, unit, color, steps):
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=val,
            title={"text": f"<b>{title}</b>", "font": {"size": 12, "color": "#94a3b8"}},
            number={"suffix": f" {unit}",
                    "font": {"size": 22, "color": color,
                             "family": "Rajdhani, sans-serif"}},
            gauge={
                "axis": {"range": [lo, hi],
                         "tickcolor": "#94a3b8",
                         "tickfont": {"color": "#94a3b8", "size": 8}},
                "bar": {"color": color, "thickness": 0.26},
                "bgcolor": "rgba(128,128,128,0.10)",
                "borderwidth": 1,
                "bordercolor": "rgba(255,255,255,0.08)",
                "steps": steps,
            },
        ))
        fig.update_layout(
            height=185,
            margin=dict(l=14, r=14, t=28, b=12),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    # ── 5 live gauges ─────────────────────────────────────────────────────
    st.markdown("#### 🧭 Live Telemetry Gauges")
    g1, g2, g3, g4, g5 = st.columns(5)

    v_col  = "#38ef7d" if 700<=v_live<=830 else "#fbbf24" if 600<=v_live<700 else "#ef4444"
    i_col  = "#38ef7d" if i_live > 0 else "#38bdf8" if i_live > -120 else "#ef4444"
    t_col  = "#38ef7d" if t_live < 38 else "#fbbf24" if t_live < 48 else "#ef4444"
    s_col  = "#38ef7d" if soc_live > 30 else "#fbbf24" if soc_live > 15 else "#ef4444"
    h_col  = "#38ef7d" if soh_live > 90 else "#fbbf24" if soh_live > 80 else "#ef4444"

    with g1:
        st.plotly_chart(_gauge("PACK VOLTAGE", v_live, 300, 880, "V", v_col, [
            {"range": [300, 600], "color": "rgba(239,68,68,.2)"},
            {"range": [600, 830], "color": "rgba(56,239,125,.15)"},
            {"range": [830, 880], "color": "rgba(239,68,68,.2)"},
        ]), use_container_width=True, key="g_v")

    with g2:
        st.plotly_chart(_gauge("PACK CURRENT", i_live, -300, 250, "A", i_col, [
            {"range": [-300, -150], "color": "rgba(239,68,68,.2)"},
            {"range": [-150, 0],    "color": "rgba(56,189,248,.15)"},
            {"range": [0, 250],     "color": "rgba(56,239,125,.15)"},
        ]), use_container_width=True, key="g_i")

    with g3:
        st.plotly_chart(_gauge("CORE TEMP", t_live, 0, 75, "°C", t_col, [
            {"range": [0,  38], "color": "rgba(56,239,125,.15)"},
            {"range": [38, 48], "color": "rgba(251,191,36,.2)"},
            {"range": [48, 75], "color": "rgba(239,68,68,.25)"},
        ]), use_container_width=True, key="g_t")

    with g4:
        st.plotly_chart(_gauge("STATE OF CHARGE", soc_live, 0, 100, "%", s_col, [
            {"range": [0,  20], "color": "rgba(239,68,68,.2)"},
            {"range": [20, 50], "color": "rgba(251,191,36,.15)"},
            {"range": [50,100], "color": "rgba(56,239,125,.15)"},
        ]), use_container_width=True, key="g_soc")

    with g5:
        st.plotly_chart(_gauge("STATE OF HEALTH", soh_live, 70, 100, "%", h_col, [
            {"range": [70, 80], "color": "rgba(239,68,68,.2)"},
            {"range": [80, 90], "color": "rgba(251,191,36,.15)"},
            {"range": [90,100], "color": "rgba(56,239,125,.15)"},
        ]), use_container_width=True, key="g_soh")

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ── derived metrics row ───────────────────────────────────────────────
    st.markdown("#### ⚡ Derived Engineering Metrics")
    dm1, dm2, dm3, dm4, dm5 = st.columns(5)
    dm1.metric("Instant Power",    f"{power_kw:+.1f} kW",  "Charging" if power_kw > 0 else "Discharging")
    dm2.metric("Est. Range",       f"{range_km} km",       f"@ {soc_live:.1f}% SoC")
    dm3.metric("HV Relay",         "CLOSED ✔" if relay_ok else "OPEN ✖",
               "Nominal" if relay_ok else "Tripped", delta_color="normal" if relay_ok else "inverse")
    dm4.metric("Pack Temp Δ",      f"{t_live - 25.0:+.1f}°C", "above ambient 25°C",
               delta_color="inverse" if t_live > 38 else "normal")
    dm5.metric("Packets Received", str(pkt_count), "UDP stream")

    # ── time-series waveform ──────────────────────────────────────────────
    if len(history) > 2:
        st.markdown("#### 📈 Real-Time Waveform — Last 30 s")
        df_h = pd.DataFrame(history)

        from plotly.subplots import make_subplots
        wc1, wc2 = st.columns(2)

        with wc1:
            fig_vi = make_subplots(specs=[[{"secondary_y": True}]])
            fig_vi.add_trace(go.Scatter(x=df_h["time"], y=df_h["packVoltage"],
                name="Voltage (V)", mode="lines+markers",
                line=dict(color="#00f2fe", width=2.4), marker=dict(size=4)),
                secondary_y=False)
            fig_vi.add_trace(go.Scatter(x=df_h["time"], y=df_h["packCurrent"],
                name="Current (A)", mode="lines",
                line=dict(color="#fbbf24", width=2, dash="dot")),
                secondary_y=True)
            fig_vi.update_layout(template="plotly_dark", height=280,
                title="Voltage & Current", margin=dict(l=40,r=40,t=40,b=30),
                legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
            st.plotly_chart(fig_vi, use_container_width=True)

        with wc2:
            fig_sc = go.Figure()
            fig_sc.add_trace(go.Scatter(x=df_h["time"], y=df_h["SoC"],
                name="SoC (%)", mode="lines", line=dict(color="#38ef7d", width=2.4)))
            fig_sc.add_trace(go.Scatter(x=df_h["time"], y=df_h["cellTemp"],
                name="Temp (°C)", mode="lines",
                line=dict(color="#ef4444", width=2, dash="dash")))
            fig_sc.add_hline(y=45, line_dash="dot", line_color="#fbbf24",
                annotation_text="Thermal Alert 45°C", annotation_font=dict(size=9, color="#fbbf24"))
            fig_sc.update_layout(template="plotly_dark", height=280,
                title="SoC & Core Temperature", margin=dict(l=40,r=40,t=40,b=30),
                legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
            st.plotly_chart(fig_sc, use_container_width=True)

    # ── JSON inspector ────────────────────────────────────────────────────
    with st.expander("🔍 Raw JSON Telemetry Inspector", expanded=False):
        st.code(json.dumps({
            "v": v_live, "i": i_live, "t": t_live,
            "soc": soc_live, "soh": soh_live,
        }, indent=2), language="json")
        st.caption(f"**Source:** {telemetry.get('source','—')}  |  "
                   f"**Sender:** {udp.last_sender}  |  "
                   f"**Packets:** {pkt_count}")

    st.markdown(
        """
        <div style="background:var(--bg-card-sub);border:1px solid var(--border);
                    border-radius:10px;padding:10px 16px;margin-top:12px;
                    font-family:'JetBrains Mono',monospace;font-size:.78rem;
                    color:var(--text-muted);line-height:1.6;">
            <b style="color:var(--cyan);">ESP32 Arduino Sketch (UDP sender):</b><br>
            UDP.beginPacket(hostIP, 4210);<br>
            UDP.printf("{\"v\":%.2f,\"i\":%.2f,\"t\":%.2f,\"soc\":%.2f,\"soh\":%.2f}",
                        packV, packI, cellT, soc, soh);<br>
            UDP.endPacket();  // call every 500 ms
        </div>
        """,
        unsafe_allow_html=True,
    )

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TAB 2 — PACK CONFIGURATOR                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝
with tab_cfg:
    st.markdown("### ⚡ Battery Energy System Configurator")
    st.caption("Virtually design, architect, and size an EV/BESS battery pack in real time based on cell electrochemistry, series-parallel topology, and thermal cooling.")

    # Multi-Factor Second-Life Battery Grading Rules
    def grade_second_life(soh, delta_r_mOhm, cell_imbalance_mV):
        if soh >= 80.0 and delta_r_mOhm < 10.0 and cell_imbalance_mV < 20:
            return "1st-Life EV Traction Certified"
        elif 70.0 <= soh < 80.0 and delta_r_mOhm < 25.0 and cell_imbalance_mV < 50:
            return "2nd-Life Stationary BESS Storage Certified (Solar/Grid)"
        elif soh < 70.0 or delta_r_mOhm >= 25.0 or cell_imbalance_mV >= 50:
            return "Recycling & Material Recovery Required (E-Waste Prevention)"
        return "Inspection Required"

    CHEM = {
        "NMC811 (3.7V, 2.5Ah)": {"v": 3.7, "c": 2.5, "family": "Lithium Nickel Manganese Cobalt (811)"},
        "LFP (3.2V, 3.2Ah)": {"v": 3.2, "c": 3.2, "family": "Lithium Iron Phosphate"},
        "LTO (2.3V, 1.5Ah)": {"v": 2.3, "c": 1.5, "family": "Lithium Titanate Oxide"},
    }

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("#### 🛠️ Pack Architecture Inputs")
            chem = st.selectbox("Select Cell Chemistry", options=list(CHEM), index=0)
            ns = st.slider("Series Cells (Ns)", min_value=12, max_value=216, value=96)
            np_cells = st.slider("Parallel Cells (Np)", min_value=1, max_value=20, value=4)
            cooling = st.selectbox("Cooling Strategy", ["Passive Air", "Forced Air", "Liquid Cold-Plate"], index=2)

            # Compatibility aliases for downstream tabs
            S = ns
            P = np_cells

            spec = CHEM[chem]
            total = ns * np_cells
            st.markdown("---")
            st.markdown(
                f"""
                <div class="tile">
                    <div class="tile-lbl">Topological String</div>
                    <div style="font-family:'Rajdhani',sans-serif;font-size:1.4rem;
                                font-weight:700;color:var(--cyan);">
                        {ns}S{np_cells}P Matrix &mdash; {total} cells
                    </div>
                    <div class="tile-sub">
                        {spec['v']} V nom &bull; {spec['c']} Ah &bull; {spec['family']}<br>
                        Cooling: {cooling}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ── Real-Time Engineering Calculations ──────────────────────────────
    v_cell = 3.7 if "NMC811" in chem else (3.2 if "LFP" in chem else 2.3)
    ah_cell = 2.5 if "NMC811" in chem else (3.2 if "LFP" in chem else 1.5)

    v_pack = ns * v_cell
    cap_pack = np_cells * ah_cell
    energy_kwh = (v_pack * cap_pack) / 1000.0
    est_mass_kg = (ns * np_cells * 0.070) * 1.3  # 70g cell + 30% packaging overhead
    est_cost_usd = (ns * np_cells * 3.50) * 1.25
    wh_kg = (energy_kwh * 1000.0) / est_mass_kg if est_mass_kg > 0 else 0.0

    # Downstream compatibility aliases
    e_kwh = energy_kwh
    mass_kg = est_mass_kg
    cost_us = est_cost_usd

    with col2:
        with st.container(border=True):
            st.markdown("#### 📊 Real-Time Sizing Metrics")

            m1, m2 = st.columns(2)
            m1.metric("Pack Voltage", f"{v_pack:.1f} V", delta=f"{ns} × {v_cell:.1f} V nom")
            m2.metric("Pack Capacity", f"{cap_pack:.1f} Ah", delta=f"{np_cells} × {ah_cell:.1f} Ah unit")

            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

            m3, m4 = st.columns(2)
            m3.metric("Pack Energy", f"{energy_kwh:.2f} kWh", delta=f"{energy_kwh * 1000:.1f} Wh total")
            m4.metric("Est. Mass", f"{est_mass_kg:.1f} kg", delta="1.30× Packaging Overhead", delta_color="off")

            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

            m5, m6 = st.columns(2)
            m5.metric("Estimated Pack BOM Cost", f"${est_cost_usd:,.2f}", delta="1.25× Cost Factor", delta_color="off")
            m6.metric("Gravimetric Density", f"{wh_kg:.1f} Wh/kg", delta=cooling)

            st.markdown("---")
            st.markdown(
                f"""
                <div class="tile" style="font-family:'JetBrains Mono',monospace;
                                         font-size:.77rem;line-height:1.65;
                                         color:var(--text-secondary);">
                    <b style="color:var(--text-muted);font-size:.7rem;
                               text-transform:uppercase;">Formulations</b><br>
                    V<sub>pack</sub> = Ns &times; V<sub>cell</sub>
                        = {ns} &times; {v_cell} =
                        <b style="color:var(--cyan);">{v_pack:.1f} V</b><br>
                    Cap<sub>pack</sub> = Np &times; Ah<sub>cell</sub>
                        = {np_cells} &times; {ah_cell} =
                        <b style="color:var(--cyan);">{cap_pack:.1f} Ah</b><br>
                    Energy<sub>kWh</sub> = (V<sub>pack</sub> &times; Cap<sub>pack</sub>) / 1000
                        = <b style="color:var(--green);">{energy_kwh:.2f} kWh</b><br>
                    Mass (kg) = (Ns &times; Np &times; 0.070) &times; 1.30
                        = <b style="color:var(--text-primary);">{est_mass_kg:.1f} kg</b><br>
                    Cost = (Ns &times; Np &times; $3.50) &times; 1.25
                        = <b style="color:var(--text-primary);">${est_cost_usd:,.2f}</b>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # ── Multi-Factor Second-Life Battery Grading Console ────────────────
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

        if "1st-Life" in certification_result:
            grade_color = "var(--green)"
            grade_icon = "🚗"
            grade_badge = "TIER 1 • AUTOMOTIVE TRACTION"
            grade_desc = "Optimal state of health and low internal resistance. Fully certified for demanding high-voltage EV road traction and dynamic regenerative acceleration."
            st.success(f"{grade_icon} **{certification_result}** — {grade_badge}")
        elif "2nd-Life" in certification_result:
            grade_color = "var(--amber)"
            grade_icon = "🔋"
            grade_badge = "TIER 2 • STATIONARY BESS STORAGE"
            grade_desc = "Capacity or impedance has degraded beyond high-C-rate automotive specs, but remains ideal for stationary grid storage, solar PV buffering, and commercial microgrids."
            st.warning(f"{grade_icon} **{certification_result}** — {grade_badge}")
        else:
            grade_color = "var(--red)"
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

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TAB 3 — MULTI-PHYSICS TRADE-OFFS                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝
with tab_trd:
    st.markdown("### 📊 Multi-Physics Battery Trade-Off Analysis")
    st.caption("Radar benchmarking · live configuration spider · NMC vs LFP comparison · C-Rate thermal simulation.")

    # ── Sub-tabs inside Trade-Off engine ─────────────────────────────────
    sub_radar, sub_compare, sub_thermal = st.tabs([
        "🕸️ Spider Chart", "📋 Spec Comparison", "🌡️ C-Rate Thermal Sim"
    ])

    # ── SUB-TAB A: Spider / Radar ─────────────────────────────────────────
    with sub_radar:
        st.markdown("##### Your Active Configuration vs Standard Benchmarks")
        st.caption(
            "Left — **Live radar** seeded from your Pack Configurator selection (0–100 scale).  "
            "Right — **NMC vs LFP** multi-config benchmark overlay (0–10 scale)."
        )

        sp_left, sp_right = st.columns(2, gap="large")

        # ── LEFT: snippet-style single-config live radar ──────────────────
        with sp_left:
            # Map chem name → radar scores (0–100 scale, matching snippet values)
            _RADAR_SCORES = {
                "NMC (3.7V, 2.5Ah)": [80, 50, 90, 60, 70],
                "LFP (3.2V, 3.2Ah)": [70, 94, 65, 95, 90],
                "LTO (2.3V, 1.5Ah)": [55, 88, 98, 92, 75],
            }
            # Gracefully fall back if chem not yet defined (Tab 2 hasn't rendered)
            _active_scores = _RADAR_SCORES.get(chem, [80, 50, 90, 60, 70])
            _PARAMS = ["Energy Density", "Thermal Safety",
                       "Charging Speed", "Lifespan", "Cost Efficiency"]

            df_live = pd.DataFrame(dict(
                r=_active_scores,
                theta=_PARAMS,
            ))
            fig_live = px.line_polar(
                df_live, r="r", theta="theta",
                line_close=True,
                range_r=[0, 100],
                template="plotly_dark",
            )
            fig_live.update_traces(
                fill="toself",
                fillcolor="rgba(0,242,254,0.18)",
                line=dict(color="#00f2fe", width=2.8),
            )
            fig_live.update_layout(
                title=dict(
                    text=f"Your Config: <b>{chem}</b>  {S}S{P}P",
                    font=dict(size=13, color="#94a3b8"),
                    x=0.5,
                ),
                height=400,
                margin=dict(l=20, r=20, t=50, b=20),
                polar=dict(
                    radialaxis=dict(
                        visible=True, range=[0, 100],
                        tickfont=dict(size=8),
                        gridcolor="rgba(255,255,255,0.12)",
                    ),
                    angularaxis=dict(
                        tickfont=dict(size=11, family="Rajdhani, sans-serif"),
                        gridcolor="rgba(255,255,255,0.10)",
                    ),
                ),
                showlegend=False,
            )
            st.plotly_chart(fig_live, use_container_width=True)

            # Live score tiles under single-config radar
            icons_m = {"Energy Density": "⚡", "Thermal Safety": "🌡️",
                       "Charging Speed": "🔋", "Lifespan": "♻️", "Cost Efficiency": "💰"}
            tile_cols = st.columns(5)
            for tc, param, sc in zip(tile_cols, _PARAMS, _active_scores):
                bar_w  = sc
                bar_c  = "#38ef7d" if sc >= 80 else "#fbbf24" if sc >= 55 else "#ef4444"
                tc.markdown(
                    f"""
                    <div class="tile" style="text-align:center;padding:8px 6px;">
                        <div style="font-size:.8rem;">{icons_m[param]}</div>
                        <div style="font-family:'Rajdhani',sans-serif;font-size:1.25rem;
                                    font-weight:700;color:{bar_c};">{sc}</div>
                        <div style="height:5px;background:rgba(255,255,255,.08);
                                    border-radius:3px;margin-top:4px;">
                            <div style="width:{bar_w}%;height:100%;
                                        background:{bar_c};border-radius:3px;"></div>
                        </div>
                        <div style="font-size:.65rem;color:var(--text-muted);
                                    margin-top:4px;">{param}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # ── RIGHT: dual-config NMC vs LFP benchmark radar ─────────────────
        with sp_right:
            PARAMS  = ["Energy Density", "Thermal Safety",
                       "Charging Speed", "Lifespan", "Cost Efficiency"]
            NMC_SCR = [9.2, 5.8, 8.0, 6.8, 6.5]
            LFP_SCR = [7.0, 9.4, 6.5, 9.5, 9.0]

            radar_df = pd.DataFrame({
                "Parameter":     PARAMS * 2,
                "Score":         NMC_SCR + LFP_SCR,
                "Configuration": (
                    ["Config A — NMC Pack"] * 5 +
                    ["Config B — LFP Pack"] * 5
                ),
            })
            fig_r = px.line_polar(
                radar_df, r="Score", theta="Parameter",
                color="Configuration", line_close=True,
                range_r=[0, 10],
                color_discrete_map={
                    "Config A — NMC Pack": "#00f2fe",
                    "Config B — LFP Pack": "#38ef7d",
                },
                template="plotly_dark",
            )
            fig_r.update_traces(fill="toself", opacity=0.35, line=dict(width=2.5))
            fig_r.update_layout(
                title=dict(
                    text="NMC vs LFP Benchmark (0–10)",
                    font=dict(size=13, color="#94a3b8"),
                    x=0.5,
                ),
                height=400,
                margin=dict(l=20, r=20, t=50, b=20),
                polar=dict(
                    radialaxis=dict(
                        visible=True, range=[0, 10],
                        tickfont=dict(size=8),
                        gridcolor="rgba(255,255,255,0.12)",
                    ),
                    angularaxis=dict(
                        tickfont=dict(size=11, family="Rajdhani, sans-serif"),
                        gridcolor="rgba(255,255,255,0.10)",
                    ),
                ),
                legend=dict(orientation="h", y=-0.08, xanchor="center", x=0.5),
            )
            st.plotly_chart(fig_r, use_container_width=True)

            # Per-parameter advantage badges
            icons = {"Energy Density": "⚡", "Thermal Safety": "🌡️",
                     "Charging Speed": "🔋", "Lifespan": "♻️", "Cost Efficiency": "💰"}
            for p, ns, ls in zip(PARAMS, NMC_SCR, LFP_SCR):
                wc = "#00f2fe" if ns >= ls else "#38ef7d"
                wl = "NMC" if ns >= ls else "LFP"
                st.markdown(
                    f"""
                    <div class="tile" style="display:flex;justify-content:space-between;
                                             align-items:center;margin-bottom:6px;">
                        <span style="font-size:.81rem;font-weight:700;
                                     color:var(--text-primary);">{icons[p]} {p}</span>
                        <div style="display:flex;gap:8px;align-items:center;">
                            <span style="font-family:'Rajdhani',sans-serif;
                                         font-size:1.05rem;font-weight:700;
                                         color:#00f2fe;">{ns}</span>
                            <span style="font-size:.68rem;color:var(--text-muted);">vs</span>
                            <span style="font-family:'Rajdhani',sans-serif;
                                         font-size:1.05rem;font-weight:700;
                                         color:#38ef7d;">{ls}</span>
                            <span style="font-size:.69rem;padding:2px 7px;
                                         border-radius:12px;border:1px solid {wc}50;
                                         color:{wc};font-weight:700;">▲ {wl}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # ── SUB-TAB B: Specification Comparison Table ─────────────────────────
    with sub_compare:
        st.markdown("##### Pack Specification Comparison — Config A (NMC) vs Config B (LFP)")
        df_cmp = pd.DataFrame({
            "Specification": [
                "Pack Energy (kWh)", "Weight (kg)", "Max C-Rate",
                "Nominal Voltage (V)", "Thermal Limit (°C)",
                "Cycle Life", "Gravimetric (Wh/kg)", "BOM Cost ($)",
            ],
            "Config A — NMC Pack": [
                "107.5 kWh", "620 kg", "4.0C", "400 V", "45°C",
                "~1,500", "173 Wh/kg", "$12,740",
            ],
            "Config B — LFP Pack": [
                "92.0 kWh", "680 kg", "2.5C", "345 V", "60°C",
                "~3,500", "135 Wh/kg", "$9,100",
            ],
            "Pack Advantage": [
                "⚡ NMC +15.8%", "⚡ NMC −60 kg", "⚡ NMC faster",
                "⚡ NMC +55 V",  "🛡️ LFP +15°C",
                "♻️ LFP +2,000", "⚡ NMC +38",   "💰 LFP −$3,640",
            ],
        })
        st.dataframe(
            df_cmp,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Specification":       st.column_config.TextColumn(width="medium"),
                "Config A — NMC Pack": st.column_config.TextColumn("Config A ⚡ NMC", width="medium"),
                "Config B — LFP Pack": st.column_config.TextColumn("Config B 🛡️ LFP", width="medium"),
                "Pack Advantage":      st.column_config.TextColumn(width="medium"),
            },
        )

        # Also show live config row for quick reference
        st.markdown("---")
        st.markdown("##### 📌 Your Configured Pack (from Pack Configurator)")
        live_row = pd.DataFrame({
            "Parameter":      ["Chemistry", "Topology", "Pack Voltage", "Pack Energy",
                               "Est. Mass", "Est. BOM Cost", "Cooling System"],
            "Your Config":    [
                chem,
                f"{S}S{P}P  ({S*P} cells)",
                f"{v_pack:.1f} V",
                f"{e_kwh:.3f} kWh",
                f"{mass_kg:.2f} kg",
                f"${cost_us:,.2f}",
                cooling,
            ],
        })
        st.dataframe(live_row, use_container_width=True, hide_index=True)

    # ── SUB-TAB C: C-Rate Thermal Simulation ─────────────────────────────
    with sub_thermal:
        st.markdown("##### 🌡️ Discharge C-Rate → Estimated Temperature Rise Curve")
        st.caption(
            "Model: `T(t) = T_amb + K·(C-Rate^α)·(1 − e^(−t/τ))` "
            "— exponential electrochemical thermal heating per chemistry."
        )

        sl_col, ch_col = st.columns([0.85, 2.15], gap="large")

        with sl_col:
            c_rate = st.slider(
                "⚡ Discharge C-Rate",
                min_value=0.5, max_value=5.0,
                value=2.0, step=0.1,
                format="%.1fC",
                help="1C = full discharge in 60 min. 5C = full discharge in 12 min.",
            )

            # Thermal model constants
            K_n, a_n, tau_n = 3.8, 1.80, 7.5   # NMC — higher resistivity
            K_l, a_l, tau_l = 3.1, 1.65, 9.0   # LFP — higher thermal stability
            T_amb = 25.0
            t_dur = min(45.0, 60.0 / c_rate)

            nmc_peak = T_amb + K_n * c_rate ** a_n
            lfp_peak = T_amb + K_l * c_rate ** a_l
            dt_adv   = nmc_peak - lfp_peak

            nmc_c = "#ef4444" if nmc_peak >= 55 else "#fbbf24" if nmc_peak >= 45 else "#38ef7d"
            lfp_c = "#ef4444" if lfp_peak >= 65 else "#fbbf24" if lfp_peak >= 55 else "#38ef7d"
            nmc_l = "⚠️ CRITICAL" if nmc_peak >= 55 else "🟡 WARNING" if nmc_peak >= 45 else "✅ NOMINAL"
            lfp_l = "⚠️ CRITICAL" if lfp_peak >= 65 else "🟡 WARNING" if lfp_peak >= 55 else "✅ NOMINAL"

            st.markdown(
                f"""
                <div class="tile" style="margin-top:10px;">
                    <div class="tile-lbl">Peak Steady-State @ {c_rate:.1f}C</div>
                    <div style="margin:8px 0 6px;">
                        <div style="font-size:.75rem;font-weight:700;
                                    color:#00f2fe;">Config A — NMC</div>
                        <div style="font-family:'Rajdhani',sans-serif;font-size:2rem;
                                    font-weight:700;color:{nmc_c};
                                    line-height:1.1;">{nmc_peak:.1f}°C</div>
                        <div style="font-size:.75rem;font-weight:700;
                                    color:{nmc_c};">{nmc_l}</div>
                    </div>
                    <div style="border-top:1px solid var(--border);padding-top:8px;">
                        <div style="font-size:.75rem;font-weight:700;
                                    color:#38ef7d;">Config B — LFP</div>
                        <div style="font-family:'Rajdhani',sans-serif;font-size:2rem;
                                    font-weight:700;color:{lfp_c};
                                    line-height:1.1;">{lfp_peak:.1f}°C</div>
                        <div style="font-size:.75rem;font-weight:700;
                                    color:{lfp_c};">{lfp_l}</div>
                    </div>
                    <div style="border-top:1px solid var(--border);
                                padding-top:8px;margin-top:8px;
                                font-family:'JetBrains Mono',monospace;
                                font-size:.70rem;color:var(--text-muted);
                                line-height:1.6;">
                        LFP advantage: {dt_adv:.1f}°C cooler<br>
                        Discharge window: {t_dur:.0f} min<br>
                        NMC: K={K_n}, α={a_n}, τ={tau_n}s<br>
                        LFP: K={K_l}, α={a_l}, τ={tau_l}s
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with ch_col:
            pts     = np.linspace(0, t_dur, 60)
            t_nmc_c = T_amb + K_n * c_rate**a_n * (1 - np.exp(-pts / tau_n))
            t_lfp_c = T_amb + K_l * c_rate**a_l * (1 - np.exp(-pts / tau_l))

            fig_th = go.Figure()
            fig_th.add_trace(go.Scatter(
                x=pts, y=t_nmc_c, name="Config A — NMC Pack",
                mode="lines", line=dict(color="#00f2fe", width=2.8),
                fill="tozeroy", fillcolor="rgba(0,242,254,0.05)",
            ))
            fig_th.add_trace(go.Scatter(
                x=pts, y=t_lfp_c, name="Config B — LFP Pack",
                mode="lines", line=dict(color="#38ef7d", width=2.8),
                fill="tozeroy", fillcolor="rgba(56,239,125,0.05)",
            ))

            # Safety threshold lines
            for y_th, col_th, label_th in [
                (45, "#fbbf24", "NMC Warning — 45°C"),
                (60, "#ef4444", "Critical Limit — 60°C"),
            ]:
                fig_th.add_hline(
                    y=y_th, line_dash="dash",
                    line_color=col_th, line_width=1.6,
                    annotation_text=label_th,
                    annotation_font=dict(size=9, color=col_th),
                )
            fig_th.add_hline(
                y=25, line_dash="dot",
                line_color="rgba(128,128,128,.4)",
                annotation_text="Ambient — 25°C",
                annotation_position="bottom right",
                annotation_font=dict(size=8, color="gray"),
            )

            fig_th.update_layout(
                title=f"Estimated Temperature Rise Curve @ {c_rate:.1f}C Discharge",
                xaxis_title="Discharge Time (min)",
                yaxis_title="Battery Pack Temperature (°C)",
                yaxis=dict(range=[20, max(70, nmc_peak + 10)]),
                template="plotly_dark",
                height=360,
                margin=dict(l=55, r=30, t=55, b=50),
                legend=dict(
                    orientation="h",
                    y=-0.22, xanchor="center", x=0.5,
                    font=dict(size=11),
                ),
            )
            st.plotly_chart(fig_th, use_container_width=True)

            # st.line_chart view (as requested in original snippet)
            with st.expander("📈 Simple Line Chart View (st.line_chart)", expanded=False):
                df_lc = pd.DataFrame({
                    "Config A — NMC (°C)": np.round(t_nmc_c, 2),
                    "Config B — LFP (°C)": np.round(t_lfp_c, 2),
                }, index=np.round(pts, 1))
                df_lc.index.name = "Time (min)"
                st.line_chart(df_lc, use_container_width=True, height=220)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TAB 4 — RISK & TRACEABILITY                                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝
with tab_rsk:
    st.markdown("### 🛡️ Risk Assessment & Battery Traceability Console")
    st.caption("Rule-based safety diagnostics + 4-cell voltage imbalance propagation tracker.")

    # live telemetry for risk
    tel_r, _, _ = udp.snapshot()
    r_volt = tel_r["packVoltage"]
    r_temp = tel_r["cellTemp"]
    r_soc  = tel_r["SoC"]
    if inject_fault:
        r_temp = max(r_temp, 54.2)
        r_volt = min(r_volt, 738.0)

    # ── Section 1: Rule-based banners ────────────────────────────────────
    st.markdown("#### 🚨 Automated Safety Recommendation Engine")

    if r_temp > 45.0:
        st.error(
            f"🔥 **CRITICAL THERMAL RISK** — Core temperature **{r_temp:.1f}°C** exceeds 45°C safety ceiling.\n\n"
            "**Recommendation:** Passive cooling is **insufficient** at this load condition.\n\n"
            "→ Upgrade to **Liquid Cooling** (≥12 L/min) — **or** — limit discharge to **≤ 1C**.\n\n"
            "→ BMS hardware relay: **prepare for emergency load isolation** if T > 55°C."
        )
    elif r_volt < 10.0:
        st.error(
            f"⚡ **DEEP DISCHARGE WARNING** — Pack voltage **{r_volt:.2f} V** below 10.0 V.\n\n"
            "**Action:** Actuating **Hardware Safety Relay** to isolate load from battery terminals.\n\n"
            "→ Risk of irreversible lithium plating and cathode dissolution.\n\n"
            "→ Estimated permanent capacity loss: **>12%** at this depth."
        )
    else:
        st.success(
            f"✅ **SYSTEM HEALTH OPTIMAL** — All parameters within normal safety margins.\n\n"
            f"→ Pack Voltage: **{r_volt:.1f} V**  |  Core Temp: **{r_temp:.1f}°C**  |  SoC: **{r_soc:.1f}%**\n\n"
            "→ BMS relay: **CLOSED** — no protective actions required."
        )

    if 38.0 < r_temp <= 45.0:
        st.warning(
            f"🌡️ **THERMAL ADVISORY** — Temperature **{r_temp:.1f}°C** in 38–45°C watch zone. "
            "Consider activating **Forced Air** cooling pre-emptively."
        )

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # snapshot tiles
    t1, t2, t3, t4 = st.columns(4)
    _vc = "#ef4444" if r_volt < 10 else "#38ef7d"
    _tc = "#ef4444" if r_temp > 45 else "#fbbf24" if r_temp > 38 else "#38ef7d"
    for col, lbl, val, sub, clr in [
        (t1, "Pack Voltage",   f"{r_volt:.1f} V",  "⚠ DEEP DISCHARGE" if r_volt < 10 else "Nominal", _vc),
        (t2, "Core Temp",      f"{r_temp:.1f}°C",  "🔥 CRITICAL" if r_temp > 45 else "✅ Optimal", _tc),
        (t3, "State of Charge",f"{r_soc:.1f}%",    f"~{int(r_soc*5.8)} km range", "#38ef7d"),
        (t4, "UDP Source",     tel_r.get("source","—")[:22],
             "Fault active" if inject_fault else "Live pipeline", "var(--cyan)"),
    ]:
        col.markdown(
            f"<div class='tile'><div class='tile-lbl'>{lbl}</div>"
            f"<div class='tile-val' style='color:{clr};'>{val}</div>"
            f"<div class='tile-sub'>{sub}</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

    # ── Section 2: 4-Cell Voltage Imbalance ──────────────────────────────
    st.markdown("#### 🔬 4-Cell Voltage Imbalance & Propagation Traceability")
    st.caption("Cell voltages derived from live pack telemetry with per-second deterministic jitter.")

    _base  = max(3.0, min(4.25, r_volt / 108.0))
    _rng   = np.random.default_rng(seed=int(time.time()) % 100)
    _off   = _rng.uniform(-0.025, 0.025, 4)
    if inject_fault:
        _off[2] = -0.38   # Cell 3 sag

    cells  = [round(_base + o, 4) for o in _off]
    v_max  = max(cells)
    v_min  = min(cells)
    v_mean = round(sum(cells) / 4, 4)
    dv     = round(v_max - v_min, 4)

    if dv > 0.200:
        imb_l, imb_c = "🔴 SEVERE IMBALANCE",   "#ef4444"
        imb_desc     = "Cell failure probable. Initiate emergency balancing."
    elif dv > 0.080:
        imb_l, imb_c = "🟡 MODERATE IMBALANCE", "#fbbf24"
        imb_desc     = "Passive balancing engaged. Monitor propagation."
    elif dv > 0.030:
        imb_l, imb_c = "🔵 MINOR IMBALANCE",    "#38bdf8"
        imb_desc     = "Within passive balancing tolerance."
    else:
        imb_l, imb_c = "🟢 BALANCED",           "#38ef7d"
        imb_desc     = "All cells within ±30 mV. Excellent uniformity."

    # bar chart
    labels  = ["V₁ — Cell 1", "V₂ — Cell 2", "V₃ — Cell 3", "V₄ — Cell 4"]
    bar_clr = []
    for cv in cells:
        d = abs(cv - v_mean)
        bar_clr.append("#ef4444" if d > 0.15 else "#fbbf24" if d > 0.05 else "#38ef7d")

    fig_b = go.Figure()
    fig_b.add_trace(go.Bar(
        x=labels, y=cells,
        marker_color=bar_clr,
        text=[f"{cv:.4f} V" for cv in cells],
        textposition="outside",
        textfont=dict(size=13, family="Rajdhani, sans-serif"),
        width=0.45,
    ))
    fig_b.add_hline(y=v_mean, line_dash="dash", line_color="#38bdf8", line_width=2,
        annotation_text=f"V̄ = {v_mean:.4f} V",
        annotation_font=dict(size=10, color="#38bdf8"))
    fig_b.add_annotation(
        x=labels[cells.index(v_min)], y=v_min,
        text=f"▼ ΔV = {dv:.4f} V",
        showarrow=True, arrowhead=2, arrowcolor=imb_c,
        font=dict(size=11, color=imb_c, family="Rajdhani, sans-serif"), ay=32,
    )
    y_pad = max(0.05, dv + 0.04)
    fig_b.update_layout(
        title="Individual Cell Terminal Voltages (V₁–V₄)",
        xaxis_title="Cell ID", yaxis_title="Terminal Voltage (V)",
        yaxis=dict(range=[v_min - y_pad, v_max + y_pad + 0.06]),
        template="plotly_dark", height=310,
        margin=dict(l=50, r=30, t=50, b=40), showlegend=False,
    )

    bc_left, bc_right = st.columns([1.65, 1], gap="large")
    with bc_left:
        st.plotly_chart(fig_b, use_container_width=True)

    with bc_right:
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        # ΔV status card
        st.markdown(
            f"""
            <div style="background:rgba(30,41,59,.7);border:1.5px solid {imb_c};
                        border-radius:14px;padding:16px 18px;margin-bottom:12px;">
                <div class="tile-lbl">ΔV Imbalance</div>
                <div style="font-family:'Rajdhani',sans-serif;font-size:2rem;
                            font-weight:700;color:{imb_c};line-height:1.1;">{dv:.4f} V</div>
                <div style="font-size:.84rem;font-weight:700;color:{imb_c};margin:3px 0 6px;">{imb_l}</div>
                <div style="font-size:.76rem;color:var(--text-secondary);line-height:1.45;">{imb_desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # per-cell rows
        for idx, (lab, cv) in enumerate(zip(["V₁","V₂","V₃","V₄"], cells)):
            dev   = round(cv - v_mean, 4)
            dc    = "#ef4444" if abs(dev) > 0.15 else "#fbbf24" if abs(dev) > 0.05 else "#38ef7d"
            ft    = " ⚠ FAULT" if inject_fault and idx == 2 else ""
            sign  = "+" if dev >= 0 else ""
            st.markdown(
                f"""
                <div class="tile" style="display:flex;justify-content:space-between;
                                         align-items:center;margin-bottom:6px;">
                    <span style="font-family:'JetBrains Mono',monospace;font-size:.8rem;
                                 font-weight:700;color:var(--text-muted);">
                        Cell {idx+1} ({lab}){ft}
                    </span>
                    <div style="text-align:right;">
                        <div style="font-family:'Rajdhani',sans-serif;font-size:1.12rem;
                                    font-weight:700;color:var(--text-primary);">{cv:.4f} V</div>
                        <div style="font-size:.72rem;font-weight:700;color:{dc};">
                            {sign}{dev:.4f} V vs V̄
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # traceability footer
    st.markdown(
        f"""
        <div class="tile" style="display:flex;gap:26px;flex-wrap:wrap;align-items:center;margin-top:6px;">
            <span style="font-size:.74rem;font-weight:700;color:var(--text-muted);">📐 TRACEABILITY</span>
            <span style="font-family:'JetBrains Mono',monospace;font-size:.77rem;color:var(--text-secondary);">
                V̄ = <b>{v_mean:.4f} V</b></span>
            <span style="font-family:'JetBrains Mono',monospace;font-size:.77rem;color:#38ef7d;">
                V_max = <b>{v_max:.4f} V</b></span>
            <span style="font-family:'JetBrains Mono',monospace;font-size:.77rem;
                         color:{'#ef4444' if inject_fault else '#fbbf24'};">
                V_min = <b>{v_min:.4f} V</b></span>
            <span style="font-family:'JetBrains Mono',monospace;font-size:.77rem;
                         font-weight:700;color:{imb_c};">
                ΔV = {dv:.4f} V &nbsp;|&nbsp; {imb_l}</span>
            <span style="font-size:.72rem;color:var(--text-muted);">
                {'Fault-Injected' if inject_fault else 'Live UDP Derived'}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

