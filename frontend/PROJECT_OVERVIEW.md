# 🚁 GARUDAVYUHA – AI-Enabled Aero Piston Engine Digital Twin (SIH 2026)

> **"PEHLE PREDICT, FIR PROTECT"**  
> *Real-time physics-coupled digital twin, neural anomaly detection, remaining useful life (RUL) analytics, and 3D interactive diagnostic Ground Control Station (GCS) for aerospace piston engines.*

---

## 📋 Executive Summary

**GARUDAVYUHA** is an advanced Ground Control Station (GCS) Digital Twin platform engineered for real-time health monitoring, neural anomaly detection, remaining useful life (RUL) estimation, and predictive maintenance of the **Rotax 914 F/UL Turbocharged 4-Stroke Boxer Engine**. 

Designed for Medium-Altitude Long-Endurance (MALE) UAV platforms (such as Tapas, Rustom, and Heron), GARUDAVYUHA bridges client-side Python execution via **Brython**, 3D WebGL CAD visualization via **Three.js**, real-time physics telemetry simulation, and explainable AI (XAI) diagnostic pipelines.

---

## 🏗️ System Architecture & Layer Breakdown

The system is structured into **5 distinct architectural layers**:

```
+-----------------------------------------------------------------------------------+
|                           LAYER 5: GCS USER INTERFACE                             |
|      Single-Page GCS (index.html), Brython Engine (py/app.py), Modular CSS       |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
|                      LAYER 4: 3D DIGITAL TWIN ENGINE VIEWER                       |
|        Three.js WebGL Engine, GLTF Loader (Rotax 914.gltf), Thermal IR Shaders     |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
|                  LAYER 3: NEURAL DIAGNOSTICS & EXPLAINABLE AI                     |
|    IsolationForest Anomaly Detector, Weibull RUL Engine, SHAP XAI Attribution    |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
|                  LAYER 2: EDGE DATA PIPELINE & LINK SECURITY                     |
|  Delta Vector Compression, HMAC-SHA256 Link Integrity, Black-Box Flight Logger   |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
|                  LAYER 1: REAL-TIME PHYSICS TELEMETRY ENGINE                      |
|       100 Hz Thermodynamic Coupling, Altitude & Desert Thermal Corrections        |
+-----------------------------------------------------------------------------------+
```

---

## ⚡ Key Architectural Features & Modules

### 1. ⚙️ Real-Time Physics Telemetry Engine (`py/telemetryEngine.py`)
- **Physics Coupling**: Simulates realistic 100 Hz thermodynamic dynamics across 9 primary sensor channels:
  - **Engine Speed** (`RPM`): Nominal 5,180 RPM
  - **Cylinder Head Temperature** (`CHT`): Nominal 136°C
  - **Exhaust Gas Temperature** (`EGT`): Nominal 715°C
  - **Main Oil Pressure**: Nominal 4.2 bar
  - **Oil Temperature**: Nominal 96°C
  - **Fuel Flow Rate**: Nominal 24.6 L/h
  - **Vibration Amplitude**: Nominal 1.35 g
  - **Battery System Voltage**: Nominal 28.2 V
  - **Injection Timing**: Nominal 24.0° BTDC
- **Fault Injection Engine**: Simulates realistic fault propagation (Injector Clogs, Oil Pressure Leaks, Turbo Boost Loss, Cylinder Fatigue) across 4 stages: `SUBTLE` $\to$ `AI_DETECTION` $\to$ `WARNING` $\to$ `CRITICAL`.

### 2. 🧠 Neural Diagnostics & Explainable AI (`py/ml_engine.py`, `py/aiDiagnostics.py`)
- **IsolationForest Anomaly Detector**: Evaluates multi-channel sensor vectors in $O(\log N)$ latency ($<1 \text{ ms}$) to calculate continuous anomaly scores ($0.00 - 1.00$).
- **Weibull RUL Hazard Model**: Uses an exponential damage propagation algorithm ($h(t) = 1 - e^{a \cdot d - b \cdot t^c}$) with shape parameter $\beta = 2.42$ and scale parameter $\eta = 1,200 \text{ hrs}$ to predict Remaining Useful Life hours along with 95% confidence intervals.
- **Dynamic Thermal Thresholding**: Applies Ideal Gas Law and ambient Z-score corrections ($T_{\text{dynamic}} = T_{\text{max, nominal}} + \alpha \cdot \frac{T_{\text{ambient}} - 15}{1.5}$) to dynamically shift thermal alarm thresholds in harsh desert operations (e.g., $160^\circ\text{C}$ dynamic threshold at $42^\circ\text{C}$ ambient vs $142^\circ\text{C}$ static threshold), preventing false alerts.
- **SHAP (Shapley Additive exPlanations) XAI**: Computes live feature attribution weights showing exact sensor contribution percentages for total operator transparency.

### 3. 🧊 Interactive 3D Digital Twin Viewer (`py/digitalTwin3D.py`)
- **High-Fidelity CAD Geometry**: Renders the Rotax 914 engine 3D mesh (`Rotax914/Rotax 914.gltf`).
- **Interactive Preset Views**: One-click camera navigation focusing on critical subsystems: Fuel Injectors, Cylinders 1–4, Oil Sump, Turbo/Exhaust, and Top-Down.
- **Visual Modes**:
  - 🔴 **Thermal IR Mode**: Dynamic false-color temperature heatmap shader.
  - 🕸️ **Wireframe Mode**: Mesh structural inspection mode.
  - 🚨 **Pulsing Alert Highlight**: Pulsing visual highlight on degraded sub-assemblies.
- **Raycasting**: Click-to-inspect mouse component selection.

### 4. 🔒 Edge Data Pipeline & Link Security (`backend/server_api.py`, `server.py`)
- **Delta-Vector Compression**: Transmits telemetry data only when parameter variance exceeds $\epsilon = 0.05$, reducing raw bandwidth from ~32 kbps to $\le 1.5 \text{ kbps}$.
- **Military Link Verification**: HMAC-SHA256 cryptographic signature headers (`X-HMAC-Token`) for tamper-evident data ingestion.
- **Black-Box Logger**: Continuous append-only logging of telemetry frames and ML inference outputs into `mission_log.csv`.

---

## 🖥️ User Interface Views (`py/app.py`, `index.html`)

GARUDAVYUHA provides 7 dedicated tactical operational views:

| View Name | Description | Key Components |
|---|---|---|
| **1. Command Center** | Main tactical GCS dashboard | Health circular gauge, readiness bar, 3D viewport hero, 3x3 sensor panel, 5 telemetry sparklines, timeline. |
| **2. 3D Digital Twin** | Fullscreen 3D CAD inspection | High-res 3D canvas, floating toolbars, subsystem status triggers, thermal IR toggle. |
| **3. AI Diagnostics & XAI** | Deep neural analysis | Anomaly score gauge, ML model latency telemetry, SHAP parameter attribution breakdown. |
| **4. RUL & Health Analytics** | Hazard curves & subsystem matrix | Weibull degradation chart (Chart.js), 8-subsystem health matrix table with remaining hours. |
| **5. Mission Simulator** | Monte Carlo scenario stress testing | Altitude ($0-25\text{k ft}$), Ambient Temp ($-40\text{ to }+50^\circ\text{C}$), Duration, and Throttle Profile sliders. |
| **6. Mission Replay** | Flight black-box playback deck | Time scrubber, playback speeds ($1\text{x}-10\text{x}$), synchronized 3D twin animation, key event bookmarks. |
| **7. Maintenance Center** | Work order & overhaul management | Automated technical work order generator, Virtual Overhaul repair action triggering subsystem reset. |

---

## 📂 Project Directory Structure

```
udaan-trail/
├── index.html                  # Main Single-Page GCS Web Application UI
├── server.py                   # Dedicated GCS Python Web Server (MIME & CORS Handler)
├── README.md                   # Quick Start Guide & Overview
├── FRONTEND_ARCHITECTURE.md    # UI/CSS Specification & Design System
├── PROJECT_OVERVIEW.md         # Full Technical Architecture Documentation
├── mission_log.csv             # Black-Box Flight Telemetry Log
├── Rotax914/                   # 3D CAD Asset Bundle
│   ├── Rotax 914.gltf          # Rotax 914 GLTF Model
│   └── buffer.bin              # Geometry Mesh Buffers
├── css/                        # Modular CSS Design System
│   ├── main.css                # Layout Grids, Color Tokens, Header HUD
│   ├── components.css          # Cards, Sparklines, Gauges, Modals
│   ├── twin3d.css              # 3D Viewport Controls & Overlays
│   └── views.css               # Section Visibility & Tab Switcher
├── py/                         # Client-Side Python Logic (Brython Runtime)
│   ├── app.py                  # Master GCS Application Controller
│   ├── telemetryEngine.py      # 100 Hz Physics Simulation Engine
│   ├── ml_engine.py            # IsolationForest, Weibull RUL & SHAP XAI Engine
│   ├── aiDiagnostics.py        # Neural Anomaly & XAI Frontend Controller
│   ├── digitalTwin3D.py        # Three.js 3D Twin & Loader Controller
│   ├── rulHealth.py            # RUL Analytics & Weibull Hazard Curves
│   ├── missionSimulator.py     # Monte Carlo Flight Scenario Simulator
│   ├── missionReplay.py        # Flight Black Box Playback Controller
│   ├── maintenanceCenter.py    # Technical Work Order & Overhaul Manager
│   ├── demoController.py       # Guided Tour Controller
│   ├── audio.py                # Web Audio Tactical Sound Synthesizer
│   └── config.py               # Sensor Definitions & Fault Scenarios
├── backend/                    # Edge Server API
│   └── server_api.py           # REST/WebSocket Data Ingestion & Delta Compressor
└── libs/                       # Third-Party Frontend Libraries
    ├── three.module.js         # Three.js 3D WebGL Library
    ├── OrbitControls.js        # Orbit Camera Controls
    ├── GLTFLoader.js           # GLTF CAD Model Loader
    ├── chart.umd.min.js        # Chart.js Telemetry Graph Library
    ├── brython.js              # Brython Python 3 Runtime
    └── brython_stdlib.js       # Brython Standard Library
```

---

## 🚀 Execution & Verification

### 1. Launching the Local Server
To launch the GCS server:
```powershell
python server.py --port 8080
```
Then open **[http://localhost:8080/index.html](http://localhost:8080/index.html)** in your web browser.

### 2. Running Headless Unit Tests
Verify standalone physics and ML engines via command line:
```powershell
# Test 100 Hz Physics Simulation & Fault Engine
python py/telemetryEngine.py

# Test IsolationForest, Weibull RUL & Dynamic Threshold Engine
python py/ml_engine.py
```

---

## 📜 Technology Stack

- **Frontend Core**: HTML5, Vanilla CSS3 (Glassmorphism design system), JavaScript (ES6+).
- **Client Python Engine**: **Brython** (Python 3 interpreter running in browser).
- **3D Graphics & WebGL**: **Three.js**, OrbitControls, GLTFLoader.
- **Data Visualization**: **Chart.js**, HTML5 2D Canvas sparklines.
- **Server Backend**: Python 3 standard library `http.server` & `socketserver` (with optional FastAPI WebSockets).
- **AI/ML Algorithms**: IsolationForest, Exponential Weibull Hazard Model, SHAP XAI Attribution.

---
*Developed for Smart India Hackathon (SIH 2026) – Aerospace & Defence Problem Statement.*
