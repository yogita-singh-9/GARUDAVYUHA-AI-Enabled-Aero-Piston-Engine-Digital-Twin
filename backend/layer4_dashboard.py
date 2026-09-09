"""
layer4_dashboard.py
====================
LAYER 4 & 5: Visualization & Human-Machine Interface (male_uav_digital_twin)

GARUDAVYUHA - AI-Enhanced Engine Digital Twin tactical dashboard.

IMPORTANT FIX vs. the earlier build: the background WebSocket client that
subscribes to Layer 2 (ws://.../ws/telemetry) is now created with
`@st.cache_resource`, which is Streamlit's true cross-rerun / cross-session
SINGLETON cache. The previous version guarded the thread-start flag inside
`st.session_state`, which is re-evaluated on every script rerun and is *not*
guaranteed to survive Streamlit's rerun model the way a module-level
singleton does - that mismatch was the root cause of the dashboard being
permanently stuck on "Waiting for telemetry from Layer 2 pipeline...".

Run standalone:  streamlit run layer4_dashboard.py
(Layer 1 and Layer 2 must already be running - see README.md)
"""
from __future__ import annotations
import base64
import collections
import json
import os
import socket
import threading
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from engine_model import load_config, active_engine_params, project_mission, rul_from_weibull

CFG = load_config()
META = active_engine_params(CFG)
NET = CFG["network"]

ORBITS = {
    "CYLINDER-1": "45deg 60deg 2.5m",
    "CYLINDER-2": "-45deg 60deg 2.5m",
    "CYLINDER-3": "135deg 60deg 2.5m",
    "CYLINDER-4": "-135deg 60deg 2.5m",
    "FUEL INJECTOR": "90deg 90deg 2m",
    "IGNITION SYSTEM": "-90deg 90deg 2m",
    "OIL SYSTEM": "0deg 110deg 2m",
    "COOLING SYSTEM": "0deg 50deg 2m",
    "EXHAUST SYSTEM": "180deg 75deg 2m",
    "SENSORS": "0deg 90deg 1.5m"
}
HERE = os.path.dirname(os.path.abspath(__file__))
WS_URL = f"ws://{NET['layer2_host']}:{NET['layer2_ws_port']}/ws/telemetry"
API_BASE = f"http://{NET['layer2_host']}:{NET['layer2_ws_port']}"

st.set_page_config(page_title="GARUDAVYUHA | AI Engine Digital Twin",
                    layout="wide", initial_sidebar_state="collapsed")

# ---------------------------------------------------------------------------
# Palette - kept identical to the original build so the CSS classes below
# reproduce the reference UI's exact look (dark navy background, cyan accents)
# ---------------------------------------------------------------------------
BG_DARK = "#05070d"
BG_CARD = "#0c1220"
CYAN = "#00f0ff"
GREEN = "#10b981"
YELLOW = "#f59e0b"
RED = "#ef4444"
MUTED = "#94a3b8"


def inject_css():
    st.markdown(f"""
    <style>
    .stApp {{ background-color: {BG_DARK}; color: white; }}
    #MainMenu, footer, header {{ visibility: hidden; }}
    .gv-card {{
        background: {BG_CARD}; border: 1px solid rgba(0,240,255,0.25);
        border-radius: 10px; padding: 14px; backdrop-filter: blur(12px);
        margin-bottom: 10px;
    }}
    .gv-label {{ color: {MUTED}; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }}
    .gv-value {{ color: {CYAN}; font-size: 26px; font-weight: 700; font-family: monospace; }}
    .gv-value-sm {{ color: white; font-size: 18px; font-weight: 600; font-family: monospace; }}
    .gv-title {{ color: {CYAN}; font-weight: 700; letter-spacing: 2px; font-size: 12px;
                 text-transform: uppercase; margin-bottom: 8px; }}
    .gv-pill {{ display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: 11px;
                font-weight:700; letter-spacing: 1px; }}
    .gv-pill-green {{ background: rgba(16,185,129,0.15); color: {GREEN}; border:1px solid {GREEN}; }}
    .gv-pill-yellow {{ background: rgba(245,158,11,0.15); color: {YELLOW}; border:1px solid {YELLOW}; }}
    .gv-pill-red {{ background: rgba(239,68,68,0.15); color: {RED}; border:1px solid {RED}; }}
    .gv-event {{ border-left: 3px solid {CYAN}; padding: 4px 10px; margin-bottom: 6px; font-size: 12px; }}
    div[data-testid="stHorizontalBlock"] {{ gap: 0.6rem; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid rgba(0,240,255,0.15); }}
    .stTabs [data-baseweb="tab"] {{ color: {MUTED}; font-size: 13px; font-weight: 600; }}
    .stTabs [aria-selected="true"] {{ color: {CYAN} !important; border-bottom: 2px solid {CYAN} !important; }}
    </style>
    """, unsafe_allow_html=True)


def severity_pill(text: str, level: str) -> str:
    cls = {"LOW": "gv-pill-green", "MEDIUM": "gv-pill-yellow", "HIGH": "gv-pill-red"}.get(level, "gv-pill-green")
    return f'<span class="gv-pill {cls}">{text}</span>'


def card(label: str, value: str, sub: str = "") -> str:
    return f"""<div class="gv-card"><div class="gv-label">{label}</div>
    <div class="gv-value">{value}</div>
    <div class="gv-label">{sub}</div></div>"""


def sparkline(values: list[float], color: str = CYAN, height: int = 60) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=values, mode="lines", line=dict(color=color, width=2),
                              fill="tozeroy", fillcolor=color.replace(")", ",0.08)").replace("rgb", "rgba") if "rgb" in color else None))
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False), showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Telemetry bus - true singleton (see module docstring for the bug this fixes)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_telemetry_bus():
    bus = {
        "latest": {},
        "history": collections.deque(maxlen=300),
        "events": collections.deque(maxlen=50),
        "connected": False,
    }
    lock = threading.Lock()

    def _worker():
        import websocket  # websocket-client
        while True:
            try:
                ws = websocket.create_connection(WS_URL, timeout=5)
                with lock:
                    bus["connected"] = True
                while True:
                    msg = ws.recv()
                    if not msg:
                        continue
                    data = json.loads(msg)
                    with lock:
                        bus["latest"] = data
                        bus["history"].append(data)
                        if data.get("anomaly_flag") or data.get("mission_abort"):
                            bus["events"].appendleft(data)
            except Exception:
                with lock:
                    bus["connected"] = False
                time.sleep(2.0)

    threading.Thread(target=_worker, daemon=True).start()
    return bus, lock


def send_udp_command(payload: dict):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(json.dumps(payload).encode(), ("127.0.0.1", NET["layer1_command_udp_port"]))
    sock.close()


@st.cache_data(show_spinner=False)
def load_glb_base64(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def model_viewer_html(glb_b64: str | None, height: int = 460, orbit: str = "35deg 75deg 105%", comp_colors: list = None) -> str:
    if not glb_b64:
        return f"""<div style="height:{height}px;display:flex;align-items:center;
        justify-content:center;color:{MUTED};border:1px dashed rgba(0,240,255,0.25);
        border-radius:10px;">No assets/engine_block.glb found.<br/>Run
        <code>python convert_gltf.py</code> to convert your GrabCAD GLTF export.</div>"""
    
    colors_js = "[" + ",".join(comp_colors or ["[1, 1, 1, 1]"] * 10) + "]"
    return f"""
    <script type="module" src="https://ajax.googleapis.com/ajax/libs/model-viewer/3.5.0/model-viewer.min.js"></script>
    <model-viewer src="data:model/gltf-binary;base64,{glb_b64}"
        style="width:100%;height:{height}px;--poster-color:transparent;background:transparent;"
        camera-controls auto-rotate auto-rotate-delay="2000" rotation-per-second="8deg"
        shadow-intensity="1" exposure="1.1"
        style-background-color="transparent"
        camera-orbit="{orbit}">
    </model-viewer>
    <script>
    (function() {{
        const mv = document.querySelector('model-viewer');
        const updateColors = () => {{
            if (!mv.model) return;
            const materials = mv.model.materials;
            if (!materials || materials.length === 0) return;
            const colors = {colors_js};
            const chunkSize = Math.floor(materials.length / 10);
            materials.forEach((m, i) => {{
                const chunkIndex = Math.min(Math.floor(i / chunkSize), 9);
                m.pbrMetallicRoughness.setBaseColorFactor(colors[chunkIndex]);
            }});
        }};
        mv.addEventListener('load', updateColors);
        updateColors();
    }})();
    </script>
    """


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
st_autorefresh(interval=1000, key="data_refresh")
inject_css()
bus, bus_lock = get_telemetry_bus()
with bus_lock:
    latest = dict(bus["latest"])
    history = list(bus["history"])
    events = list(bus["events"])
    connected = bus["connected"]

top_l, top_r = st.columns([3, 1])
with top_l:
    st.markdown(f"""<div style="display:flex;align-items:center;gap:10px;">
        <span style="font-size:22px;font-weight:800;color:white;letter-spacing:2px;">GARUDAVYUHA</span>
        <span style="color:{MUTED};font-size:12px;">AI-ENHANCED ENGINE DIGITAL TWIN &nbsp;|&nbsp;
        {META['display_name']}</span></div>""", unsafe_allow_html=True)
with top_r:
    status = "LIVE" if connected else "OFFLINE"
    color = GREEN if connected else RED
    st.markdown(f"""<div style="text-align:right;">
        <span class="gv-pill {'gv-pill-green' if connected else 'gv-pill-red'}">&#9679; {status}</span>
        &nbsp;<span style="color:{MUTED};font-size:12px;">{time.strftime('%d %b %Y, %H:%M:%S')}</span>
        </div>""", unsafe_allow_html=True)

if not connected:
    st.warning("Waiting for telemetry from Layer 2 pipeline... make sure "
               "`layer1_physics.py` and `uvicorn layer2_pipeline:app` are both running "
               "(see README.md).")

tabs = st.tabs([
    "\U0001F6F0\uFE0F Command Center", "\U0001F527 3D Digital Twin", "\U0001F9E0 AI Diagnostics",
    "\U0001F4C8 RUL & Health", "\U0001F3AF Mission Simulator", "\u23EA Mission Replay",
    "\u2699\uFE0F Maintenance Center",
])

glb_b64 = load_glb_base64(os.path.join(HERE, "assets", "engine_block.glb"))
history_df = pd.DataFrame(history) if history else pd.DataFrame()

# =========================================================== COMMAND CENTER
with tabs[0]:
    c1, c2, c3 = st.columns([1, 1.6, 1])
    with c1:
        st.markdown('<div class="gv-title">MISSION OVERVIEW</div>', unsafe_allow_html=True)
        st.markdown(card("UAV ID", "UDAAN-01", "MALE Digital Twin"), unsafe_allow_html=True)
        st.markdown(card("MISSION TYPE", "ISR - LONG ENDURANCE"), unsafe_allow_html=True)

        health_pct = round((1 - latest.get("anomaly_score", 0.02)) * 100, 1) if latest else 98.0
        st.markdown('<div class="gv-title">ENGINE HEALTH</div>', unsafe_allow_html=True)
        st.markdown(card("OVERALL", f"{health_pct}%",
                          "HEALTHY" if health_pct > 80 else ("WARNING" if health_pct > 60 else "CRITICAL")),
                    unsafe_allow_html=True)

        rul_hours, rul_ci = rul_from_weibull(latest.get("flight_hours", 480.0),
                                              META["weibull_shape"], META["weibull_scale"])
        st.markdown('<div class="gv-title">ESTIMATED RUL</div>', unsafe_allow_html=True)
        st.markdown(card(f"&plusmn; {rul_ci:.1f} HRS (95% CI)", f"{rul_hours:.1f} HRS"),
                     unsafe_allow_html=True)

        st.markdown('<div class="gv-title">ACTIVE ALERTS</div>', unsafe_allow_html=True)
        if events:
            for ev in events[:4]:
                st.markdown(f'<div class="gv-event">{ev.get("most_likely_fault", "Event")} '
                            f'&mdash; {time.strftime("%H:%M:%S", time.localtime(ev.get("timestamp", time.time())))}</div>',
                            unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="gv-event" style="border-color:{GREEN}">No active alerts</div>',
                        unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="gv-title">3D DIGITAL TWIN &mdash; ' + META["display_name"].upper() + '</div>',
                    unsafe_allow_html=True)
        st.components.v1.html(model_viewer_html(glb_b64, height=420), height=430)

    with c3:
        st.markdown('<div class="gv-title">LIVE SENSOR PANEL</div>', unsafe_allow_html=True)
        s1, s2 = st.columns(2)
        with s1:
            st.markdown(card("RPM", f"{latest.get('rpm', 0):.0f}"), unsafe_allow_html=True)
            st.markdown(card("EGT &deg;C", f"{latest.get('egt', 0):.0f}"), unsafe_allow_html=True)
            st.markdown(card("FUEL FLOW", f"{latest.get('fuel_flow', 0):.1f}"), unsafe_allow_html=True)
        with s2:
            st.markdown(card("CHT &deg;C", f"{latest.get('cht', 0):.0f}"), unsafe_allow_html=True)
            st.markdown(card("VIBRATION g", f"{latest.get('vibration', 0):.2f}"), unsafe_allow_html=True)
            st.markdown(card("OIL BAR", f"{latest.get('oil_pressure', 0):.1f}"), unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)
    b1, b2, b3, b4, b5 = st.columns(5)
    trend_cols = [("rpm", "RPM"), ("cht", "CHT (\u00b0C)"), ("egt", "EGT (\u00b0C)"),
                  ("oil_pressure", "OIL (bar)"), ("vibration", "VIBRATION (g)")]
    for col, (field, label) in zip((b1, b2, b3, b4, b5), trend_cols):
        with col:
            st.markdown(f'<div class="gv-label">{label}</div>', unsafe_allow_html=True)
            series = history_df[field].tail(60).tolist() if field in history_df else []
            st.plotly_chart(sparkline(series), key=f"spark_{field}", width="stretch", config={"displayModeBar": False})
            st.markdown(f'<div class="gv-value-sm">{latest.get(field, 0):.2f}</div>' if latest else "-",
                        unsafe_allow_html=True)

# =========================================================== 3D DIGITAL TWIN
with tabs[1]:
    left, right = st.columns([1, 3])
    components = [
        ("CYLINDER-1", "cht"), ("CYLINDER-2", "cht"), ("CYLINDER-3", "cht"), ("CYLINDER-4", "cht"),
        ("FUEL INJECTOR", "fuel_flow"), ("IGNITION SYSTEM", "rpm"), ("OIL SYSTEM", "oil_pressure"),
        ("COOLING SYSTEM", "cht"), ("EXHAUST SYSTEM", "egt"), ("SENSORS", "vibration"),
    ]
    with left:
        st.markdown('<div class="gv-title">COMPONENT HEALTH</div>', unsafe_allow_html=True)
        anomaly = latest.get("anomaly_score", 0.02) if latest else 0.02
        top_feat = (latest.get("xai_contributions") or [{}])[0].get("feature") if latest else None
        comp_colors = []
        for i, (name, feat) in enumerate(components):
            level = "HEALTHY"
            color_rgba = "[1, 1, 1, 1]"
            if feat == top_feat and anomaly > 0.66:
                level = "CRITICAL"
                color_rgba = "[1, 0.2, 0.2, 1]"
            elif feat == top_feat and anomaly > 0.33:
                level = "WARNING"
                color_rgba = "[1, 1, 0, 1]"
            comp_colors.append(color_rgba)
            dot = {"HEALTHY": "🟢", "WARNING": "🟡", "CRITICAL": "🔴"}[level]
            if st.button(f"{dot} {name} - {level}", key=f"comp_btn_{name}", use_container_width=True):
                st.session_state.orbit_comp = name
    with right:
        st.markdown('<div class="gv-title">3D DIGITAL TWIN &mdash; AERO PISTON ENGINE</div>', unsafe_allow_html=True)
        orbit = ORBITS.get(st.session_state.get("orbit_comp", ""), "35deg 75deg 105%")
        st.components.v1.html(model_viewer_html(glb_b64, height=520, orbit=orbit, comp_colors=comp_colors), height=530)

# =========================================================== AI DIAGNOSTICS
with tabs[2]:
    d1, d2 = st.columns([1, 2])
    with d1:
        score = latest.get("anomaly_score", 0.0) if latest else 0.0
        severity = latest.get("severity", "LOW") if latest else "LOW"
        st.markdown('<div class="gv-title">NEURAL ANOMALY SCORE</div>', unsafe_allow_html=True)
        st.markdown(card(severity, f"{score:.2f}", "SCALE: 0.00 (NOMINAL) TO 1.00 (ANOMALOUS)"),
                    unsafe_allow_html=True)
        st.markdown('<div class="gv-title">MOST LIKELY FAULT</div>', unsafe_allow_html=True)
        st.markdown(card(f"Confidence {latest.get('confidence_pct', 0):.0f}%",
                          latest.get("most_likely_fault", "Nominal Operation")), unsafe_allow_html=True)
        st.markdown('<div class="gv-title">ACTIVE ML PIPELINE (3 MODELS)</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="gv-event">1. Isolation Forest (Aero-Trained)<br/><span style="color:{MUTED};">Unsupervised multivariate outlier scoring</span></div>
        <div class="gv-event">2. Weibull / NASA C-MAPSS RUL Model<br/><span style="color:{MUTED};">Exponential degradation & knee-of-curve projection</span></div>
        <div class="gv-event">3. Z-Score Parameter Attribution<br/><span style="color:{MUTED};">Explainable per-channel deviation ranking</span></div>
        """, unsafe_allow_html=True)
        st.caption("Simulated AI demonstration engine \u2014 trained on physics-generated healthy baseline.")
    with d2:
        st.markdown('<div class="gv-title">Explainable AI (XAI): Parameter Contribution (Z-Score Attribution)</div>',
                    unsafe_allow_html=True)
        contribs = latest.get("xai_contributions", []) if latest else []
        if contribs:
            fig = go.Figure(go.Bar(
                x=[c["z_score"] for c in contribs], y=[c["feature"].upper() for c in contribs],
                orientation="h", marker_color=[RED if abs(c["z_score"]) > 2 else CYAN for c in contribs],
            ))
            fig.update_layout(height=260, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               font_color="white", margin=dict(l=10, r=10, t=10, b=10),
                               xaxis_title="Z-score vs healthy baseline")
            st.plotly_chart(fig, key="chart_xai", width="stretch", config={"displayModeBar": False})
            top = contribs[0]
            st.info(f"AI INTERPRETATION: **{top['feature'].upper()}** deviates "
                    f"{top['z_score']:.2f}\u03c3 from the learned healthy operating pattern.")
        else:
            st.info("Awaiting telemetry to compute parameter attribution.")
        st.markdown('<div class="gv-title">ACTIONABLE TACTICAL ADVISORY</div>', unsafe_allow_html=True)
        advisory = "All parameters nominal. Continue standard monitoring."
        if contribs and contribs[0]["feature"] in ("cht",):
            advisory = "Inspect cooling circuit and coolant flow; monitor CHT trend closely."
        elif contribs and contribs[0]["feature"] == "vibration":
            advisory = "Inspect mounting hardware and bearing wear; monitor vibration RMS."
        elif contribs and contribs[0]["feature"] == "fuel_flow":
            advisory = "Inspect fuel injector circuit and perform cleaning/replacement if necessary."
        st.success(advisory)

# =========================================================== RUL & HEALTH
with tabs[3]:
    rul_hours, rul_ci = rul_from_weibull(latest.get("flight_hours", 480.0) if latest else 480.0,
                                          META["weibull_shape"], META["weibull_scale"])
    h1, h2 = st.columns([1, 3])
    with h1:
        st.markdown('<div class="gv-title">ESTIMATED REMAINING USEFUL LIFE</div>', unsafe_allow_html=True)
        st.markdown(card("MEDIUM TERM", f"{rul_hours:.1f} HOURS", f"&plusmn; {rul_ci:.1f} HRS (95% CI)"),
                    unsafe_allow_html=True)
        st.markdown('<div class="gv-title">WEAR HAZARD MODEL (WEIBULL 2-PARAM)</div>', unsafe_allow_html=True)
        st.markdown(card("SHAPE (\u03b2)", f"{META['weibull_shape']}", "Wear-out phase"), unsafe_allow_html=True)
        st.markdown(card("SCALE (\u03b7)", f"{META['weibull_scale']:.0f} hrs"), unsafe_allow_html=True)
    with h2:
        st.markdown('<div class="gv-title">HEALTH DEGRADATION TRAJECTORY (HISTORICAL vs PROJECTED)</div>',
                    unsafe_allow_html=True)
        elapsed = latest.get("flight_hours", 480.0) if latest else 480.0
        hist_x = list(range(int(elapsed) - 100, int(elapsed) + 1))
        hist_y = [max(0, 100 - (x - hist_x[0]) * 0.05) for x in hist_x]
        proj_x = list(range(int(elapsed), int(elapsed) + 60))
        proj_y = [max(0, hist_y[-1] - (x - proj_x[0]) * 1.1) for x in proj_x]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist_x, y=hist_y, name="Historical Health",
                                  line=dict(color=CYAN, width=2)))
        fig.add_trace(go.Scatter(x=proj_x, y=proj_y, name="Projected Degradation",
                                  line=dict(color=YELLOW, width=2, dash="dot")))
        fig.update_layout(height=360, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font_color="white", legend=dict(orientation="h", y=1.1),
                           xaxis_title="Flight Hours", yaxis_title="Health %")
        st.plotly_chart(fig, key="chart_rul", width="stretch", config={"displayModeBar": False})

        st.markdown('<div class="gv-title">COMPONENT-WISE HEALTH BREAKDOWN</div>', unsafe_allow_html=True)
        subsystems = [
            ("Turbocharger & Wastegate Assembly", 0.94), ("Liquid Cooling Jackets & Pump", 0.95),
            ("Integrated Reduction Gearbox & Clutch", 0.95), ("Cylinder Heads & Combustion Chamber", 0.96),
            ("Dry-Sump Lubrication & Oil Cooler", 0.97), ("Fuel Injection & Induction", 0.98),
            ("Dual Electronic CDI & Ignition Leads", 0.99), ("ECU / TCU Avionics & Sensor Harness", 0.99),
        ]
        rows = []
        for name, base_health in subsystems:
            adj_health = max(0.5, base_health - (latest.get("anomaly_score", 0) * 0.15 if latest else 0))
            est_remaining = round(adj_health * META["weibull_scale"] * 0.9)
            priority = "LOW" if adj_health > 0.9 else ("MEDIUM" if adj_health > 0.75 else "HIGH")
            rows.append({"Subsystem": name, "Health": f"{adj_health*100:.0f}%",
                         "Condition": "OPTIMAL" if adj_health > 0.9 else "MONITOR",
                         "Est. Remaining (hrs)": est_remaining, "Maintenance Priority": priority})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# =========================================================== MISSION SIMULATOR
with tabs[4]:
    s1, s2 = st.columns([1, 2])
    with s1:
        st.markdown('<div class="gv-title">FLIGHT SCENARIO INPUTS (MONTE CARLO ENGINE)</div>', unsafe_allow_html=True)
        alt = st.slider("Flight Altitude (ft)", 0, 25000, 18200, step=100)
        amb = st.slider("Ambient Temp (\u00b0C, DAT)", -40, 55, 42)
        dur = st.slider("Mission Duration (hrs)", 0.5, 14.0, 8.5, step=0.5)
        throttle = st.selectbox("Throttle Profile", [
            "Idle Taxi (30% MCP)", "Standard Cruise (75% MCP)",
            "High Alt Loiter (65% MCP)", "Rapid Throttle (100% MCP)",
        ], index=1)
        run = st.button("\u25B6 RUN MISSION SIMULATION", use_container_width=True)
        send = st.button("\u26A1 SEND SCENARIO TO LAYER 1 (LIVE)", use_container_width=True)
        if send:
            send_udp_command({"ambient_temp": amb, "altitude_ft": alt, "duration_hrs": dur})
            st.success("Scenario sent to Layer 1 successfully.")
    with s2:
        if run or True:
            result = project_mission(alt, amb, dur, throttle, META,
                                      start_flight_hours=latest.get("flight_hours", 480.0) if latest else 480.0)
            m1, m2, m3 = st.columns(3)
            m1.markdown(card("MISSION RISK", result["risk"]), unsafe_allow_html=True)
            m2.markdown(card("PROJECTED CHT PEAK", f"{result['cht_peak']:.1f}\u00b0C",
                              f"Dynamic limit: {result['dynamic_limit']:.1f}\u00b0C"), unsafe_allow_html=True)
            m3.markdown(card("PROJECTED EGT PEAK", f"{result['egt_peak']:.0f}\u00b0C",
                              f"Normal limit: {result['egt_limit']:.0f}\u00b0C"), unsafe_allow_html=True)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=result["hours"], y=result["cht_curve"], name="CHT (\u00b0C)",
                                      line=dict(color=CYAN, width=2)))
            fig.add_trace(go.Scatter(x=result["hours"], y=result["egt_curve"], name="EGT (\u00b0C)",
                                      line=dict(color=YELLOW, width=2), yaxis="y2"))
            fig.add_hline(y=result["dynamic_limit"], line_dash="dash", line_color=RED,
                          annotation_text="Dynamic CHT limit")
            fig.update_layout(
                height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="white", legend=dict(orientation="h", y=1.1),
                xaxis_title="Mission Elapsed (hrs)",
                yaxis=dict(title="CHT \u00b0C"), yaxis2=dict(title="EGT \u00b0C", overlaying="y", side="right"),
            )
            st.plotly_chart(fig, key="chart_sim", width="stretch", config={"displayModeBar": False})
            st.markdown(f"**AI Tactical Recommendation:** RUL impact "
                        f"{result['rul_impact_hours']:.1f}h &nbsp;|&nbsp; projected end-of-mission health "
                        f"{result['end_health_pct']:.0f}%", unsafe_allow_html=True)

# =========================================================== MISSION REPLAY
with tabs[5]:
    r1, r2 = st.columns([1, 2])
    uploaded = st.file_uploader("Upload mission_log.csv (Layer 5 black box)", type="csv")
    df_replay = None
    if uploaded is not None:
        df_replay = pd.read_csv(uploaded)
    elif os.path.exists(os.path.join(HERE, "mission_log.csv")):
        try:
            df_replay = pd.read_csv(os.path.join(HERE, "mission_log.csv"))
        except Exception:
            df_replay = None

    if df_replay is not None and len(df_replay) > 0:
        st.success(f"Loaded {len(df_replay)} recorded telemetry rows.")
        idx = st.slider("Scrub timeline", 0, len(df_replay) - 1, len(df_replay) - 1)
        row = df_replay.iloc[idx]
        with r1:
            st.markdown('<div class="gv-title">RECORDED TELEMETRY (BLACK BOX)</div>', unsafe_allow_html=True)
            for label, field in [("Flight Hours", "flight_hours"), ("Engine Speed (RPM)", "rpm"),
                                  ("Cylinder Head Temp", "cht"), ("Exhaust Gas Temp", "egt"),
                                  ("Fuel Flow", "fuel_flow"), ("Vibration RMS", "vibration"),
                                  ("Anomaly Score", "anomaly_score")]:
                if field in row:
                    st.markdown(card(label, f"{row[field]:.2f}"), unsafe_allow_html=True)
        with r2:
            st.markdown('<div class="gv-title">REPLAY TREND</div>', unsafe_allow_html=True)
            fig = go.Figure()
            for field, color in [("cht", CYAN), ("egt", YELLOW), ("vibration", RED)]:
                if field in df_replay:
                    fig.add_trace(go.Scatter(y=df_replay[field].iloc[:idx + 1], name=field.upper(),
                                              line=dict(color=color, width=2)))
            fig.update_layout(height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="white", legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, key="chart_replay", width="stretch", config={"displayModeBar": False})
    else:
        st.info("No recorded flight data yet. Let Layer 1/2 run for a while, "
                "or upload a mission_log.csv exported from a previous session.")

# =========================================================== MAINTENANCE CENTER
with tabs[6]:
    st.markdown('<div class="gv-title">PREDICTIVE MAINTENANCE & TECHNICAL OVERHAUL CENTER</div>',
                unsafe_allow_html=True)
    st.caption("AI-Driven Prognostics to Service-Window Mapping \u2014 AEROSPACE DEFENCE PROTOCOL")

    rul_hours, _ = rul_from_weibull(latest.get("flight_hours", 480.0) if latest else 480.0,
                                     META["weibull_shape"], META["weibull_scale"])
    work_orders = [
        {"id": "WO-ROUTINE-50H", "title": "Dry-Sump Lubrication & Filter", "priority": "SCHEDULED PREVENTIVE",
         "detail": "Standard 50-hour oil and filter replacement; check magnetic chip detector for ferrous particles."},
    ]
    if latest and latest.get("severity") in ("MEDIUM", "HIGH"):
        work_orders.insert(0, {
            "id": "WO-URGENT-AI", "title": latest.get("most_likely_fault", "Anomaly Investigation"),
            "priority": "AI-FLAGGED " + latest.get("severity", ""),
            "detail": f"Isolation Forest anomaly score {latest.get('anomaly_score', 0):.2f}. "
                      f"Confidence {latest.get('confidence_pct', 0):.0f}%.",
        })
    if rul_hours < 100:
        work_orders.append({
            "id": "WO-RUL-WINDOW", "title": "Schedule Overhaul Window", "priority": "MEDIUM",
            "detail": f"Estimated RUL {rul_hours:.0f} hours \u2014 plan depot-level inspection before threshold.",
        })

    cols = st.columns(3)
    for i, wo in enumerate(work_orders):
        with cols[i % 3]:
            pill = "gv-pill-red" if "AI-FLAGGED" in wo["priority"] or "HIGH" in wo["priority"] else "gv-pill-yellow"
            st.markdown(f"""<div class="gv-card">
                <div class="gv-label">{wo['id']}</div>
                <span class="gv-pill {pill}">{wo['priority']}</span>
                <div style="font-weight:700;margin:8px 0 4px;">{wo['title']}</div>
                <div class="gv-label" style="text-transform:none;">{wo['detail']}</div>
                </div>""", unsafe_allow_html=True)
            st.button("\U0001F527 Virtual Overhaul", key=f"vo_{i}")

    st.markdown('<div class="gv-title">LAYER 6 &mdash; FEDERATED FLEET MANAGEMENT</div>', unsafe_allow_html=True)
    if st.button("\U0001F4E4 Export Fleet Node Config (fleet_node_01.json)"):
        try:
            import requests
            resp = requests.get(f"{API_BASE}/api/fleet/export", timeout=5)
            st.success(f"Exported: {resp.json().get('node_id')}")
        except Exception as e:
            st.error(f"Could not reach Layer 2 API: {e}")

# ---------------------------------------------------------------------------
# Live auto-refresh 
# ---------------------------------------------------------------------------
# Live auto-refresh is now handled by streamlit-autorefresh at the top of the script.
