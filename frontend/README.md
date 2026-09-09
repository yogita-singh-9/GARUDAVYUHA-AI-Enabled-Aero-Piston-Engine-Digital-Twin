# GARUDAVYUHA – AI-Enabled Aero Piston Engine Digital Twin (SIH 2026)

> **"PEHLE PREDICT, FIR PROTECT"**  
> *Real-time physics-coupled digital twin, neural anomaly detection, remaining useful life (RUL) analytics, and 3D interactive diagnostic GCS for aerospace piston engines.*

---

## 🚁 Overview

**GARUDAVYUHA** is a Ground Control Station (GCS) Digital Twin interface designed for real-time health monitoring, fault prediction, and maintenance planning of the **Rotax 914 F/UL Turbocharged 4-Stroke Boxer Engine** (deployed on Medium-Altitude Long-Endurance (MALE) UAV platforms like Tapas, Rustom, and Heron).

The system executes full client-side Python logic via **Brython** paired with high-performance **Three.js WebGL 3D rendering** for interactive CAD component diagnostics.

---

## 🌟 Key Features

### 1. 🧊 Interactive 3D Digital Twin Engine Viewer
- **Rotax 914 GLTF Model**: High-fidelity 3D CAD visualization (`Rotax914/Rotax 914.gltf`).
- **Dynamic Camera Presets**: Subsystem focus targets (Fuel Injectors, Cylinders, Turbo/Exhaust, Oil Sump, Top-Down).
- **Visualization Modes**:
  - 🔴 **Thermal IR Mode**: Dynamic false-color temperature heatmap rendering per subsystem.
  - 🕸️ **Wireframe Mode**: Structural mesh inspection.
  - 🚨 **Critical Pulsing Glow**: Pulsing visual highlight on degraded engine sub-assemblies.
  - 🔄 **Auto Rotation & Raycasting**: Interactive click-to-inspect component selection.

### 2. ⚡ Real-Time Physics Telemetry Engine (`100 Hz`)
- Simulates realistic thermodynamic behavior across **9 key engine parameters**:
  - Engine Speed (`RPM`)
  - Cylinder Head Temperature (`CHT`)
  - Exhaust Gas Temperature (`EGT`)
  - Main Oil Pressure & Temperature
  - Fuel Flow & Injection Timing
  - Mechanical Vibration (`g`)
  - Battery System Voltage
- Dynamic HTML5 Canvas sparklines & multi-channel dashboard telemetry graphs.

### 3. 🧠 AI Diagnostics & Explainable AI (XAI)
- **Multi-Model ML Pipeline Simulation**:
  - **Bi-LSTM Autoencoder**: Multi-channel reconstruction error tracking.
  - **Isolation Forest**: Unsupervised multivariate outlier detection.
  - **XGBoost Classifier**: 6-class aerodynamic fault classification.
- **SHAP (Shapley Additive exPlanations)**: Live parameter attribution breakdown showing exact sensor contributions to anomaly scores.

### 4. ⏳ RUL & Health Analytics (Weibull Hazard Model)
- **Remaining Useful Life Estimation**: Uses a 2-parameter Weibull wear-out hazard model (`β = 2.42`, `η = 1,200 hrs`).
- **Interactive Degradation Curves**: Historical health trajectory vs. projected wear bounds (Chart.js integration).
- **Component-Wise Health Matrix**: Live state & remaining operating hours for 8 core engine subsystems.

### 5. 🛫 Flight Scenario & Mission Simulator
- **Monte Carlo Flight Engine**: Predicts mission outcome based on:
  - Altitude (`0` to `25,000 ft`)
  - Outside Ambient Temp (`-40°C` to `+50°C`)
  - Flight Duration (`1` to `14 Hours`)
  - Throttle Profiles (Loiter 65%, Cruise 75%, High Dash 90%, Tactical Variable)
- **One-Click Stress Injection**: Apply simulated mission wear directly to the 3D twin.

### 6. 📼 Black-Box Mission Replay
- Scrubbable flight playback deck (`1x`, `2x`, `5x`, `10x` speeds).
- Key flight bookmarks (Takeoff, FL160 climb, Vibration Onset, RTB Commanded).
- Synchronized telemetry & 3D model status updates.

### 7. 🛠️ Predictive Maintenance & Overhaul Center
- Automated technical work order generation based on AI fault severity.
- **Virtual Overhaul Action**: One-click component repair simulation resetting subsystem health.
- Printable / Exportable GCS Technical Work Orders.

---

## 🛠️ Architecture & Tech Stack

```
udaan-trail/
├── index.html                  # Main Single-Page GCS Web Application UI
├── server.py                   # Lightweight GCS Python HTTP Server (CORS & Custom MIME types)
├── README.md                   # Project Documentation
├── Rotax914/                   # 3D Asset Bundle
│   ├── Rotax 914.gltf          # Rotax 914 Engine CAD Model
│   └── buffer.bin              # Binary Geometry & Mesh Buffers
├── css/                        # Modular CSS3 Stylesheets
│   ├── main.css                # Layout Grid, Color Tokens & Base Styles
│   ├── components.css          # Cards, Buttons, Modals & HUD Widgets
│   ├── twin3d.css              # 3D Viewport Controls & Overlays
│   └── views.css               # Section-specific Styles
├── py/                         # Core Python Client Logic (Brython Engine)
│   ├── app.py                  # Master Application Controller & Navigation
│   ├── digitalTwin3D.py        # Three.js 3D Twin & Loader Controller
│   ├── telemetryEngine.py      # Real-Time Telemetry Simulation Engine
│   ├── aiDiagnostics.py        # Neural Anomaly & SHAP XAI Engine
│   ├── rulHealth.py            # RUL Analytics & Weibull Hazard Curves
│   ├── missionSimulator.py     # Monte Carlo Flight Scenario Engine
│   ├── missionReplay.py        # Flight Black Box Playback System
│   ├── maintenanceCenter.py    # Technical Work Order & Overhaul Manager
│   ├── demoController.py       # Guided Tour Controller
│   ├── audio.py                # Web Audio API Tactical Sound Synthesizer
│   └── config.py               # Engine Specs, Sensor Limits & Fault Data
└── libs/                       # Vendored JavaScript Libraries
    ├── three.module.js         # Three.js 3D WebGL Library
    ├── OrbitControls.js        # Orbit Camera Controls
    ├── GLTFLoader.js           # GLTF/GLB Asset Loader
    ├── chart.umd.min.js        # Chart.js Analytics Library
    ├── brython.js              # Brython Python 3 Client Runtime
    └── brython_stdlib.js       # Brython Standard Library
```

---

## 🚀 How to Run Locally

### Prerequisites
- **Python 3.8+** installed on your system.

### Quick Start

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/harshita-21art/udaan-trail.git
   cd udaan-trail
   ```

2. **Launch the Dedicated GCS Python Server**:
   ```bash
   python server.py
   ```
   *Or specify a custom port:*
   ```bash
   python server.py --port 8080
   ```

3. **Open in Browser**:
   Navigate to:
   [http://localhost:8080/index.html](http://localhost:8080/index.html)

---

## 🎮 3D Digital Twin Controls

| Action | Control |
|---|---|
| **Rotate View** | Left Click + Drag |
| **Pan Camera** | Right Click + Drag / Shift + Left Click |
| **Zoom** | Mouse Wheel Scroll |
| **Select Subsystem** | Left Click directly on 3D mesh component |
| **Thermal IR Mode** | Click 🔥 icon in 3D floating tool bar |
| **Wireframe Mode** | Click 🔳 icon in 3D floating tool bar |
| **Reset View** | Click 🗜️ icon in 3D floating tool bar |

---

## 📜 License & Citation

Developed for **Smart India Hackathon (SIH 2026)** – Aerospace & Defence Problem Statement.  
*All telemetry and health metrics are simulated for demonstration purposes.*
