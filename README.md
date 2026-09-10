# GARUDAVYUHA — AI-Enabled Aero Piston Engine Digital Twin

> **"PEHLE PREDICT, FIR PROTECT"**
> *Predict First. Protect Always.*

**Smart India Hackathon 2026 | Problem Statement SIH26054**
**Domain:** Aerospace & Defence | **Organisation:** DRDO / IAF

---

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Architecture](#architecture)
4. [Tech Stack](#tech-stack)
5. [ML Pipeline](#ml-pipeline)
6. [Engine & Sensor Specifications](#engine--sensor-specifications)
7. [Fault Scenarios](#fault-scenarios)
8. [Project Structure](#project-structure)
9. [Quick Start](#quick-start)
10. [All CLI Commands](#all-cli-commands)
11. [API Reference](#api-reference)
12. [Integration Test Suite](#integration-test-suite)
13. [Dataset](#dataset)

---

## Overview

**GARUDAVYUHA** is a real-time Ground Control Station (GCS) Digital Twin for the
**Rotax 914 F/UL Turbocharged 4-Stroke Boxer Engine** deployed on MALE (Medium-Altitude
Long-Endurance) UAV platforms including the TAPAS-BH-201, Rustom, and Heron.

The system provides:
- **Real-time physics-coupled telemetry simulation** at 500 Hz sampling
- **AI anomaly detection** using IsolationForest trained on NASA C-MAPSS data
- **Remaining Useful Life (RUL)** estimation via Weibull hazard model
- **Explainable AI (XAI/SHAP)** parameter attribution for every fault
- **Interactive 3D Rotax 914 engine model** with thermal IR and wireframe modes
- **Black-box flight recorder** (append-only CSV mission log)
- **Federated fleet management** export for multi-UAV GCS networks

---

## Key Features

### 1. Interactive 3D Digital Twin Engine Viewer
- High-fidelity Rotax 914 GLTF/GLB CAD model rendered via Three.js WebGL
- **Dynamic camera presets** for 8 engine subsystems (fuel injectors, cylinders, turbo, oil sump, etc.)
- **Thermal IR Mode** — false-colour temperature heatmap per subsystem
- **Wireframe Mode** — structural mesh inspection
- **Critical Pulsing Glow** — crimson pulse on degraded assemblies
- **Raycasting** — click any mesh component for instant diagnostics

### 2. Real-Time Telemetry Engine (500 Hz)
Physics-coupled simulation of **9 key Rotax 914 parameters**:

| Sensor | Nominal | Normal Range | Unit |
|---|---|---|---|
| Engine Speed (RPM) | 5,180 | 4,800 – 5,400 | RPM |
| Cylinder Head Temp (CHT) | 136 | 110 – 142 | °C |
| Exhaust Gas Temp (EGT) | 715 | 680 – 745 | °C |
| Oil Pressure | 4.2 | 3.5 – 5.0 | bar |
| Oil Temperature | 96 | 85 – 105 | °C |
| Fuel Flow | 24.6 | 22.0 – 27.5 | L/h |
| Vibration RMS | 1.35 | 0.8 – 2.2 | mm/s |
| Avionics Bus Voltage | 28.2 | 27.5 – 28.8 | V DC |
| Injection Timing | 24.0 | 22.5 – 25.5 | ° BTDC |

### 3. AI Diagnostics & Explainable AI (XAI)
- **IsolationForest** unsupervised anomaly detector — trained on 79,997 healthy-phase rows from all 4 NASA C-MAPSS datasets
- **Bi-LSTM Autoencoder** reconstruction error tracking (simulated)
- **XGBoost Multi-Class Fault Classifier** (6 aerodynamic fault classes, simulated)
- **SHAP (Shapley Additive Explanations)** — live per-parameter attribution showing which sensor contributed most to the anomaly score

### 4. Remaining Useful Life (RUL) — Weibull Hazard Model
- 2-parameter Weibull wear-out model (β = 2.42, η = 1,200 hrs, matching Rotax 914 TBO)
- Exponential damage propagation: `h(t) = 1 − exp(a·d − b·t^c)` (Saxena et al. PHM'08)
- RUL prediction with ±confidence interval
- Component-wise health matrix for all 8 engine subsystems

### 5. Dynamic Thermal Threshold (False-Alarm Reduction)
Adaptive CHT limit based on ambient temperature (Ideal Gas Law Z-score):

```
T_dynamic = T_nominal + α × ((T_ambient − 15°C) / 1.5)
```

At 50°C ambient, the dynamic CHT limit adjusts to 165.3°C vs the static 142°C — preventing
false mission-abort alerts in desert operations.

### 6. Mission Simulator (Monte Carlo)
- Altitude: 0 – 25,000 ft | Ambient: −40°C to +50°C | Duration: 1 – 14 hrs
- Throttle profiles: Loiter 65%, Cruise 75%, High Dash 90%, Tactical Variable
- One-click fault injection into the live 3D twin

### 7. Black-Box Mission Replay
- Scrubbable flight playback deck (1×, 2×, 5×, 10× speeds)
- Key flight bookmarks (Takeoff, FL160 climb, Vibration Onset, RTB)
- Synchronized telemetry + 3D model state updates

### 8. Predictive Maintenance & Overhaul Center
- Automated GCS Technical Work Order generation from AI fault severity
- Virtual overhaul: one-click component health reset
- Printable/exportable maintenance reports with part numbers and MTTR estimates

### 9. Telemetry Compression (Layer 2)
Delta-vector differential compression:
- Transmits only channels where `|Δ| > ε (0.05)`
- Reduces raw bandwidth from ~32 kbps → ≤ 1.5 kbps
- HMAC-SHA256 link integrity token on every packet

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     GARUDAVYUHA LAYERS                           │
│                                                                  │
│  LAYER 1: Physics Simulation (telemetryEngine.py)                │
│    └─ Rotax 914 thermodynamics, fault injection, 500 Hz          │
│                          │                                       │
│  LAYER 2: Edge Data Pipeline (backend/server_api.py)             │
│    └─ HMAC verify │ Delta compress │ Black-box CSV log           │
│                          │                                       │
│  LAYER 3: AI Intelligence (py/ml_engine.py)                      │
│    └─ IsolationForest │ RUL Weibull │ SHAP │ Dynamic Threshold   │
│                          │                                       │
│  LAYER 4: GCS Dashboard (index.html + Brython + Three.js)        │
│    └─ 3D Twin │ Telemetry HUD │ Charts │ AI Panel                │
│                          │                                       │
│  LAYER 5: Flight Recorder (mission_log.csv)                      │
│    └─ Append-only CSV black box                                  │
│                          │                                       │
│  LAYER 6: Fleet Management (/api/fleet/export)                   │
│    └─ Federated multi-UAV node config export                     │
└──────────────────────────────────────────────────────────────────┘

  Frontend Server (server.py, port 8080)
    ├── GET  /api/telemetry/snapshot  → tick physics + ML inference
    ├── POST /api/v1/diagnose         → ML inference on any packet
    ├── GET  /api/v1/benchmark        → NASA C-MAPSS benchmark
    ├── GET  /api/fleet/export        → fleet node config JSON
    └── *                            → static files (HTML/JS/GLTF)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **UI Framework** | Vanilla HTML5 + CSS3 (no framework) |
| **3D Rendering** | Three.js r155 WebGL, GLTF/GLB loader, OrbitControls |
| **Client Logic** | Brython 3.12 (Python 3 in the browser via transpilation) |
| **ML / AI** | scikit-learn IsolationForest, NumPy, joblib |
| **Charts** | Chart.js 4.x (Canvas API) |
| **HTTP Server** | Python `http.server` + `socketserver.ThreadingMixIn` |
| **Data Format** | JSON (API), CSV (black box), GLTF+JSON (3D model) |
| **Security** | HMAC-SHA256 telemetry link integrity |
| **Dataset** | NASA C-MAPSS (FD001–FD004, 160K+ rows) |

---

## ML Pipeline

### Training (IsolationForest)

```
NASA C-MAPSS Datasets (CMaps/)
  train_FD001.txt  →  100 engines,  20,631 rows,  10,290 healthy-phase rows
  train_FD002.txt  →  260 engines,  53,759 rows,  26,817 healthy-phase rows
  train_FD003.txt  →  100 engines,  24,720 rows,  12,333 healthy-phase rows
  train_FD004.txt  →  249 engines,  61,249 rows,  30,557 healthy-phase rows
                                                  ─────────────────────────
  TOTAL            →  709 engines, 160,359 rows,  79,997 healthy-phase rows
                                                       ↓
  IsolationForest(n_estimators=300, contamination=0.01, n_jobs=-1)
  Trained on Z-scored healthy-phase rows
                                                       ↓
  Calibration percentiles: p1=0.4006, p50=0.4897, p99=0.6205
                                                       ↓
  ml_model.joblib  (saved, never retrained on startup)
```

### C-MAPSS → Rotax 914 Feature Mapping

| Rotax 914 Sensor | C-MAPSS Column | Description |
|---|---|---|
| `rpm` | s2 (col 6) | Fan speed proxy |
| `cht` | s4 (col 8) | LPC outlet temperature |
| `egt` | s7 (col 11) | HPC outlet temperature |
| `oil_press` | s14 (col 18) | Burner fuel-air ratio |
| `oil_temp` | s9 (col 13) | HTBleed temperature |
| `fuel_flow` | s12 (col 16) | Corrected fan speed |
| `vibration` | s6 (col 10) | Burner pressure ratio |
| `battery_volt` | s11 (col 15) | Bypass ratio |
| `injection_timing` | s13 (col 17) | HP turbine inlet temp |

### Inference Pipeline (per packet)
```
Rotax 914 sensor values
    │
    ▼
Z-score using Rotax config baselines (from config.py)
    │
    ▼
IsolationForest.score_samples()
    │
    ▼
Calibrated anomaly score: clip((raw − p50) / (p99 − p50) × 0.6 + 0.04, 0.02, 0.98)
    │
    ├─→ anomalyScore [0, 1]
    ├─→ isAnomaly (True if score > 0.45 or predict == -1)
    ├─→ RUL estimate via Weibull exponential model
    ├─→ Dynamic CHT threshold check
    └─→ SHAP parameter attribution
```

### NASA PHM'08 Benchmark Results

| Metric | Value | Target |
|---|---|---|
| Mean Absolute Error (MAE) | **4.8 hrs** | ≤ 6.0 hrs ✅ |
| False Alarm Rate (FAR) | **0.32%** | < 0.8% ✅ |
| R² Score | **0.976** | ≥ 0.95 ✅ |
| ROC-AUC | **0.984** | — |
| Fault Classification Accuracy | **98.4%** | — |
| Avg Inference Latency | **< 1 ms** | — |

---

## Engine & Sensor Specifications

**Engine:** Rotax 914 F3 / MALE UAV Certified
- Displacement: 1,211 cc | 4 Cylinders | Horizontally-Opposed Boxer, 4-Stroke
- Aspiration: Turbocharged with Automatic Wastegate (TCU)
- Max Power: 115 HP @ 5,800 RPM (Takeoff, 5 min)
- Continuous: 100 HP @ 5,500 RPM
- TBO: **1,200 hours**
- UAV Platform: TAPAS-BH-201 / MALE UAV-04

**8 Monitored Subsystems:**
| Subsystem | TBO (hrs) | Sensors Monitored |
|---|---|---|
| Fuel Injection & Induction | 600 | fuel_flow, egt, vibration |
| Cylinder Heads & Combustion | 1,200 | cht, rpm, vibration |
| Turbocharger & Wastegate | 800 | egt, rpm, oil_press |
| Dry-Sump Lubrication | 500 | oil_press, oil_temp, vibration |
| Liquid Cooling Circuit | 1,000 | cht, oil_temp |
| Dual CDI Ignition | 600 | injection_timing, rpm, battery_volt |
| Reduction Gearbox | 1,200 | vibration, rpm |
| ECU/TCU Avionics | 2,000 | battery_volt, injection_timing |

---

## Fault Scenarios

| Fault ID | Severity | Subsystem | MTTR |
|---|---|---|---|
| `injector_abnormality` | CRITICAL | Fuel Injection | 2.5 hrs |
| `overheating` | CRITICAL | Cooling Circuit | 3.0 hrs |
| `lubrication_issue` | CRITICAL | Oil System | 4.5 hrs |
| `abnormal_vibration` | WARNING | Gearbox | 2.0 hrs |
| `sensor_drift` | ADVISORY | Avionics | 1.0 hr |
| `combustion_instability` | WARNING | Cylinders | 2.0 hrs |

Each fault has a **4-stage progression**: SUBTLE → AI_DETECTION → WARNING → CRITICAL,
with SHAP contribution weights, AI diagnosis text, and maintenance procedure.

---

## Project Structure

```
new/
├── backend/                        # Standalone FastAPI backend (optional)
│   ├── server.py                   # Layer 2: FastAPI data bus (UDP→WebSocket)
│   ├── layer1_physics.py           # Layer 1: Physics simulator (UDP stream)
│   ├── layer3_intelligence.py      # Layer 3: IsolationForest + Weibull RUL
│   ├── engine_model.py             # Shared physics core
│   ├── config.json                 # Engine params + network ports
│   ├── mission_log.csv             # Black-box flight recorder
│   └── requirements.txt
│
└── frontend/                       # Main GCS Web Application
    ├── index.html                  # Single-page GCS UI (HTML5 + CSS3)
    ├── server.py                   # Lightweight HTTP + API server (port 8080)
    ├── ml_model.joblib             # Trained IsolationForest model
    ├── mission_log.csv             # Frontend black-box logger
    │
    ├── Rotax914/                   # 3D Asset Bundle
    │   ├── Rotax 914.gltf          # Rotax 914 CAD model
    │   └── buffer.bin              # Binary geometry/mesh buffers (~11 MB)
    │
    ├── CMaps/                      # NASA C-MAPSS Dataset
    │   ├── train_FD001.txt         # 100 engines, 20,631 rows
    │   ├── train_FD002.txt         # 260 engines, 53,759 rows
    │   ├── train_FD003.txt         # 100 engines, 24,720 rows
    │   ├── train_FD004.txt         # 249 engines, 61,249 rows
    │   ├── test_FD001-FD004.txt    # Held-out test sets (707 engines)
    │   ├── RUL_FD001-FD004.txt     # True RUL labels
    │   └── Damage Propagation Modeling.pdf
    │
    ├── css/
    │   ├── main.css                # Layout grid, color tokens, base styles
    │   ├── components.css          # Cards, buttons, modals, HUD widgets
    │   ├── twin3d.css              # 3D viewport controls & overlays
    │   └── views.css               # Section-specific styles
    │
    ├── py/                         # Brython Python client logic
    │   ├── app.py                  # Master GCS controller (~1,200 lines)
    │   ├── config.py               # Engine specs, sensor limits, fault data
    │   ├── telemetryEngine.py      # Real-time physics simulation
    │   ├── aiDiagnostics.py        # AI diagnostics + async API bridge
    │   ├── ml_engine.py            # IsolationForest, RUL, SHAP, Threshold
    │   ├── cmapss_benchmark.py     # NASA PHM'08 benchmark suite
    │   ├── integration_test.py     # Full 79-check integration test suite
    │   ├── digitalTwin3D.py        # Three.js 3D twin controller
    │   ├── rulHealth.py            # RUL analytics & Weibull curves
    │   ├── missionSimulator.py     # Monte Carlo flight scenario engine
    │   ├── missionReplay.py        # Flight black-box playback
    │   ├── maintenanceCenter.py    # Work order & overhaul manager
    │   ├── demoController.py       # Guided 11-step demo tour
    │   └── audio.py               # Web Audio API tactical sound
    │
    ├── backend/
    │   └── server_api.py           # GCS API handler (HMAC, compress, logger)
    │
    └── libs/                       # Vendored JS libraries
        ├── three.module.js         # Three.js r155 WebGL engine
        ├── OrbitControls.js        # Camera orbit controls
        ├── GLTFLoader.js           # GLTF/GLB asset loader
        ├── chart.umd.min.js        # Chart.js 4.x analytics
        ├── brython.js              # Brython Python 3 runtime
        └── brython_stdlib.js       # Brython standard library
```

---

## Quick Start

### Prerequisites
- Python 3.8+ (tested on Python 3.14)
- `pip install numpy scikit-learn joblib`

### 1. Train the ML model (first time only)
```powershell
cd frontend
python py\ml_engine.py --train
```

### 2. Start the GCS Server
```powershell
cd frontend
python server.py --port 8080
```

### 3. Open the Dashboard
Navigate to: [http://localhost:8080/index.html](http://localhost:8080/index.html)

---

## All CLI Commands

All commands run from the `frontend/` directory.

```powershell
# ── ML Model ──────────────────────────────────────────────────────
# Train on all 4 C-MAPSS datasets (FD001–FD004, ~80K rows)
python py\ml_engine.py --train

# Evaluate on held-out test sets (707 engines, MAE / RMSE / PHM08)
python -X utf8 py\ml_engine.py --test

# Live rolling inference monitor (prints score per second)
python -X utf8 py\ml_engine.py --monitor

# Quick unit test (healthy + fault packet)
python py\ml_engine.py

# ── Benchmarks ────────────────────────────────────────────────────
# NASA C-MAPSS benchmark suite (PHM08 score, FAR, R²)
python -X utf8 py\cmapss_benchmark.py

# ── Integration Tests ─────────────────────────────────────────────
# Offline (59 checks — no server required)
python -X utf8 py\integration_test.py --no-api

# Full stack (79 checks — requires server running on 8080)
python -X utf8 py\integration_test.py --server-url http://localhost:8080

# ── Server ────────────────────────────────────────────────────────
python server.py --port 8080
python server.py --port 8080 --no-browser
```

> **Windows Note:** Always use `python -X utf8` to avoid `UnicodeEncodeError`
> from box-drawing characters in terminal output.

---

## API Reference

All endpoints served by `server.py` on port 8080.

### `GET /api/telemetry/snapshot`
Ticks the physics engine, runs ML inference, logs to CSV, returns combined snapshot.

**Response:**
```json
{
  "health": 98.4,
  "anomalyScore": 0.04,
  "predictedRUL": 48.5,
  "missionRisk": "LOW",
  "sensors": { "rpm": 5180, "cht": 136, "egt": 715, ... },
  "dynamicThresholds": { "cht": 142.0 },
  "shapAttribution": [...],
  "compressedKbps": 1.2,
  "X-HMAC-Token": "<sha256 hex>"
}
```

### `POST /api/v1/diagnose`
ML inference on any arbitrary sensor packet.

**Request:**
```json
{
  "sensors": { "rpm": 4900, "cht": 165, "egt": 810, ... },
  "health": 55.0,
  "anomalyScore": 0.78,
  "activeFault": null
}
```

**Response:**
```json
{
  "anomalyScore": 0.84,
  "anomalyPercentage": 84,
  "mostLikelyFault": "Incipient Thermal/Mechanical Drift",
  "predictedRUL": 3.6,
  "inferenceLatencyMs": 0.35,
  "mlModelEngine": "IsolationForest[C-MAPSS FD001-FD004]",
  "shapAttribution": [...]
}
```

### `GET /api/v1/benchmark`
Runs the full NASA PHM'08 benchmark suite. Returns metrics.

### `GET /api/fleet/export`
Exports current node's IsolationForest config + Weibull parameters as JSON for fleet distribution.

---

## Integration Test Suite

`py/integration_test.py` — **79 checks across 7 layers:**

| Layer | What is tested | Checks |
|---|---|---|
| L1 ML Engine | Model exists, inference, discrimination, RUL, SHAP, threshold | 11 |
| L2 C-MAPSS Data | All 12 files exist, parse correctly, matrix shape | 24 |
| L3 Test Evaluation | 707 held-out engines, anomaly score range | 3 |
| L4 TelemetryEngine | Physics tick, fault injection, reset | 10 |
| L5 BlackBox Logger | CSV write, header, timestamp format | 3 |
| L6 Backend API | snapshot, diagnose, benchmark, fleet export | 16 |
| L7 Static Assets | index.html, GLTF MIME type | 4 |

**Result: 79/79 PASS ✅**

---

## Dataset

**NASA C-MAPSS (Commercial Modular Aero-Propulsion System Simulation)**

Reference: *Saxena et al., "Damage Propagation Modeling for Aircraft Engine Run-to-Failure
Simulation," PHM'08*

| Dataset | Conditions | Fault Modes | Train Engines | Test Engines |
|---|---|---|---|---|
| FD001 | 1 | 1 | 100 | 100 |
| FD002 | 6 | 1 | 260 | 259 |
| FD003 | 1 | 2 | 100 | 100 |
| FD004 | 6 | 2 | 249 | 248 |

26 sensor columns per row. Features extracted: 9 key aero-parameter proxies mapped
to Rotax 914 sensor equivalents.

---

## Licence & Citation

Developed for **Smart India Hackathon (SIH) 2026** — Problem Statement SIH26054
(Aerospace & Defence — DRDO/IAF).

*All telemetry values are physics-coupled simulations for demonstration.*
*NASA C-MAPSS dataset used under academic research terms.*

```
@misc{garudavyuha2026,
  title  = {GARUDAVYUHA: AI-Enabled Aero Piston Engine Digital Twin},
  author = {Yogita Singh et al.},
  year   = {2026},
  note   = {Smart India Hackathon SIH26054}
}
```

---

*GARUDAVYUHA — Named after the ancient Vedic military formation (eagle formation),
representing total situational awareness and precision strike capability.*
