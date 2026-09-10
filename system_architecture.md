# GARUDAVYUHA — System Architecture & Workflow
> Derived from source code analysis, not documentation.

---

## High-Level Overview

The project is a **dual-world system**: a **Python backend** that owns the real physics and ML computation, and a **browser frontend** that is itself a full Python runtime (via Brython) driving the UI. Both worlds can operate independently — the frontend falls back to self-simulation if the backend is not running.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        BROWSER  (frontend/)                             │
│                                                                         │
│   index.html  ──loads──▶  Brython Runtime (brython.js)                  │
│                                    │                                    │
│                                    ▼                                    │
│   py/app.py  (Master Controller)  ◀──── orchestrates all modules        │
│      │                                                                  │
│      ├── py/telemetryEngine.py  ← Physics sim at 4 Hz (250 ms timer)    │
│      ├── py/ml_engine.py        ← In-browser ML scoring + RUL           │
│      ├── py/aiDiagnostics.py    ← XAI attribution display logic         │
│      ├── py/digitalTwin3D.py    ← Three.js 3D model controller (Python) │
│      ├── py/rulHealth.py        ← Weibull hazard chart rendering         │
│      ├── py/missionSimulator.py ← What-if thermodynamic projections      │
│      ├── py/missionReplay.py    ← CSV black-box playback                 │
│      ├── py/maintenanceCenter.py← Work order & overhaul triggers         │
│      ├── py/demoController.py   ← Guided fault demo tour                 │
│      └── py/audio.py            ← Web Audio tactical sounds              │
│                                                                         │
│   (Optional WebSocket uplink to backend on ws://localhost:8000/ws/telemetry)
└─────────────────────────────────────────────────────────────────────────┘
             ▲ WebSocket (if backend is alive)
             │
┌─────────────────────────────────────────────────────────────────────────┐
│                       BACKEND  (backend/)                               │
│                                                                         │
│   layer1_physics.py  ─── UDP 9999 ───▶  backend/server.py (FastAPI)    │
│          ▲                                        │                     │
│          │ UDP 9998                               ├── layer3_intelligence.py (ML)
│   (commands from                                 ├── mission_log.csv   │
│    dashboard)                                    ├── /ws/telemetry     │
│                                                  ├── /api/latest        │
│                                                  ├── /api/history       │
│                                                  ├── /api/fleet/export  │
│                                                  └── /api/v1/diagnose   │
│                                                                         │
│   engine_model.py  (shared physics core, imported by both L1 and L3)   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Deep-Dive

### 1. `engine_model.py` — Shared Physics Core (backend)

This is the **single source of truth** for every equation. It is imported by both the physics simulator (`layer1_physics.py`) and the ML training engine (`layer3_intelligence.py`). Key functions it exposes:

| Function | What it does |
|---|---|
| `load_config()` | Reads `config.json` — engine params, ports, HMAC secret |
| `active_engine_params()` | Returns Rotax 914 or VRDE Tapas params based on `active_engine` key |
| `compute_packet()` | Generates a single telemetry snapshot at given ambient/altitude/hours |
| `step_state()` | Advances the simulation by one timestep, updating flight hours |
| `residual_features()` | Computes *actual − expected* corrections per sensor (used for ML) |
| `dynamic_thermal_limit()` | `T_limit = T_max + α × ((T_ambient − T_std) / 1.5)` — adaptive CHT threshold |
| `health_fraction()` | Weibull reliability `R(t) = exp(−(t/scale)^shape)` |
| `rul_from_weibull()` | Inverts Weibull CDF to get remaining hours + 95% CI |

> **Swap engines instantly**: just change `"active_engine": "vrde_tapas"` in `config.json`. Zero code changes.

---

### 2. `layer1_physics.py` — Physics Simulator (backend)

- **Main loop**: runs every **0.5 seconds** (`physics_loop_seconds` from config).
- Calls `step_state()` → gets a sensor packet → **HMAC-SHA256 signs** it with the shared secret → sends it as a UDP datagram to `127.0.0.1:9999`.
- Also spins up a **second UDP listener on port 9998** (command socket) on a background thread.
  - Accepts JSON like `{"fault": "overheat"}`, `{"ambient_temp": 45}`, `{"fault": "clear"}`.
  - These commands come from the Streamlit dashboard's Mission Simulator tab.
- **State tracked**: `flight_hours`, `ambient_temp`, `altitude_ft`, `fault_injected`.

---

### 3. `backend/server.py` — FastAPI Pipeline Hub (backend)

This is `layer2_pipeline.py` — the central data bus. It runs via `uvicorn` on port `8000`.

**On startup (`lifespan` context):**
1. Ensures `mission_log.csv` has headers.
2. Opens a UDP datagram endpoint on `127.0.0.1:9999` via `asyncio.DatagramProtocol`.
3. Instantiates `AdvancedDiagnosticEngine` (Layer 3) — which auto-trains if no model file exists.

**On every UDP packet received (`UDPIntakeProtocol._handle`):**
1. Parse JSON envelope.
2. `verify_signature()` — HMAC-SHA256 check. **Rejects packet** if invalid.
3. Pass raw packet to `ml_engine.evaluate_packet()` → get diagnostics.
4. Merge: `enriched = {**raw_packet, **diagnostics}`.
5. Append enriched row to `mission_log.csv` (async, with lock).
6. `manager.broadcast(enriched)` → push to **all connected WebSocket clients**.
7. Log alert events if `anomaly_flag=True` or `mission_abort=True`.

**REST / WebSocket API exposed:**
| Endpoint | Purpose |
|---|---|
| `GET /api/latest` | Last enriched packet (polling fallback) |
| `GET /api/history?limit=N` | Last N enriched packets from in-memory deque |
| `GET /api/events` | Alert log (anomaly flags, HMAC rejects, threshold breaches) |
| `GET /api/fleet/export` | Export fleet node config → writes `fleet_node_01.json` |
| `GET /api/health` | Server health, client count, row count |
| `POST /api/v1/diagnose` | On-demand ML inference on arbitrary sensor payload |
| `WS /ws/telemetry` | Live push feed; sends latest packet immediately on connect |

---

### 4. `layer3_intelligence.py` — ML Engine (backend)

The `AdvancedDiagnosticEngine` class is loaded once and reused per packet.

**Training (runs once, auto-triggered if no model file):**
1. Generates **healthy baseline** across full operational envelope (−10..50°C, 0..22,000 ft, full life span) using `compute_packet()`.
2. Computes **physics-corrected residuals** (`actual − expected`) for 6 features: `rpm, cht, egt, fuel_flow, oil_pressure, vibration`.
3. Trains `IsolationForest(n_estimators=150, contamination=0.01)` on those **residuals** (not raw values).
4. Saves three `.joblib` files: the model, the scaler, and baseline percentile stats.

**Per-packet inference (`evaluate_packet`):**
1. Compute residuals for incoming packet.
2. `StandardScaler.transform()` → normalize.
3. `model.decision_function()` → calibrate against baseline p50/p1 percentiles → `instant_score ∈ [0, 1]`.
4. Apply **EMA smoother** (α=0.3) → prevents jitter: `score = 0.3 × instant + 0.7 × prev`.
5. **XAI attribution**: z-score each residual channel against baseline noise std → rank which sensor deviated most.
6. **Fault mapping**: top-contributing sensor → human-readable fault label (e.g., `cht` → `"Overheat / Cooling Circuit Fault"`).
7. Compute **RUL** via Weibull inversion + 95% CI.
8. Compute **dynamic thermal limit** for current ambient temperature.
9. Return structured diagnostic dict.

---

### 5. Frontend — Brython Python Runtime (`frontend/py/`)

The browser loads `index.html`, which boots Brython. Brython then runs `py/app.py` as Python 3 in the browser.

#### `py/telemetryEngine.py` — In-Browser Physics Simulation

- Runs a `timer.set_interval()` loop at **250 ms (4 Hz)** using the browser's timer API.
- Maintains full sensor state: `currentSensors`, `targetSensors`, `sensorHistory[]` with exponential approach smoothing (`alpha=0.12`) + Gaussian noise.
- **Fault injection engine**: 4-stage progression `SUBTLE → AI_DETECTION → WARNING → CRITICAL` driven by `faultProgression ∈ [0, 1]`.
- **Dual-mode**: if a backend WebSocket is available (`connectWebSocket()`), switches `dataSource = 'websocket'` and applies `applyExternalTelemetry()` from backend data. If WS closes, auto-reverts to `'simulated'` mode.
- **Event bus**: `on(event, callback)` / `emit(event, data)` — all other modules subscribe to `'telemetry'` events.

#### `py/ml_engine.py` — In-Browser ML (NASA C-MAPSS)

- Trained on all 4 NASA C-MAPSS datasets (`FD001–FD004` from `frontend/CMaps/`).
- `ml_model.joblib` is loaded in-browser via Brython + joblib for O(log N) inference.
- Also contains the **Weibull/exponential RUL damage propagation** model.
- SHAP-style feature attribution computed as z-score deviations per sensor channel.

#### `py/digitalTwin3D.py` — 3D Engine Viewer (Python → Three.js)

- Python code that **controls JavaScript Three.js objects** via Brython's `window.THREE` bridge.
- Loads `Rotax914/Rotax 914.gltf` using `GLTFLoader`.
- Builds a map of named mesh groups → subsystems (cylinders, injectors, oil sump, turbo, etc.).
- **Thermal IR Mode**: replaces materials with gradient heatmap shader based on current CHT values.
- **Wireframe Mode**: toggles mesh wireframe property.
- **Raycasting**: mouse click → `Raycaster.intersectObjects()` → `onSelectComponent` callback → triggers diagnostics for that part.
- **Camera animation**: smooth lerp to preset views (top-down, cylinder bank, injector closeup, etc.).
- **Pulsing alert**: `Math.sin(time)` driven emissive glow on critically degraded subsystem meshes.

#### `py/missionSimulator.py` — What-If Projections

- Purely **client-side thermodynamic projection** (no backend call).
- Given altitude, ambient temp, duration, throttle profile → computes projected peak CHT/EGT/oil temp using density corrections (`σ = exp(−alt/29000)`) and turbocharger boost ratio.
- Returns time-series curves (CHT, EGT, health) for Chart.js rendering.
- Sends scenario as UDP to Layer 1 backend command port if backend is connected.

#### `py/missionReplay.py` — Black-Box Playback

- Parses `mission_log.csv` (uploaded or fetched from backend).
- Scrubs through frames, calling `handleReplayFrameUpdate(frame)` in `app.py` on each step.
- Synchronized to 3D twin: highlights which subsystem was in distress at each timestamp.

#### `py/maintenanceCenter.py` — Work Order Manager

- On overhaul trigger: calls `telemetryEngine.overhaulSubsystem(id)` → resets that subsystem's health to 98.8%.
- Generates a work order text: part name, recommended action, estimated hours.
- Calls `/api/fleet/export` on backend to snapshot fleet node config → `fleet_node_01.json`.

---

## End-to-End Data Flow (When Backend is Running)

```
[layer1_physics.py]
  └─ every 500ms: compute_packet() → HMAC-sign → UDP→9999

[backend/server.py (FastAPI + asyncio)]
  └─ UDPIntakeProtocol.datagram_received()
      ├─ verify HMAC signature
      ├─ ml_engine.evaluate_packet()  ← layer3_intelligence.py
      │     ├─ residual_features()
      │     ├─ IsolationForest.decision_function() → EMA score
      │     ├─ XAI z-score attribution
      │     └─ rul_from_weibull()
      ├─ append_csv_row() → mission_log.csv
      └─ manager.broadcast() → WebSocket /ws/telemetry

[Browser – telemetryEngine.py]
  └─ wsConnection.onmessage → applyExternalTelemetry()
      └─ emit('telemetry', snapshot)

[Browser – app.py subscribes to 'telemetry']
  ├─ update health gauge, readiness bar, anomaly score, RUL
  ├─ update 9 sensor cards
  ├─ update 5 sparkline graphs
  ├─ digitalTwin3D.updateSubsystemHealth() → thermal IR + pulsing alert
  └─ aiDiagnostics.update() → XAI attribution bar charts
```

## Standalone Mode (No Backend)

```
[browser/py/telemetryEngine.py – internal loop at 4Hz]
  └─ updatePhysicsSimulation()
      └─ fault progression → sensor target shifts → exponential approach → emit('telemetry')

[Everything else is identical — the frontend is fully self-contained]
```

---

## Security Model

| Mechanism | Implementation |
|---|---|
| Telemetry link integrity | HMAC-SHA256 on every UDP packet (`secret_key_hex` in `config.json`) |
| Reject tampered packets | `hmac.compare_digest()` — timing-safe; rejected packets logged to `/api/events` |
| CORS | `allow_origins=["*"]` on FastAPI (permissive, demo environment) |

---

## Key Design Decisions (From Code)

1. **Residuals, not raw values for ML**: The Isolation Forest is trained on `actual − expected` sensor readings, not raw sensor values. This removes environmental variation (altitude, ambient temp, normal aging) so the model only sees mechanical anomalies.

2. **EMA smoothing on anomaly score**: `score = 0.3 × instant + 0.7 × prev` — prevents dashboard jitter from single noisy packets.

3. **Baseline percentile calibration**: Score is calibrated against the baseline's own `decision_function` p50/p1 — not an assumed center of 0 — preventing score saturation bugs.

4. **Symmetric thermal correction**: The dynamic thermal limit shifts up *and* down with ambient temperature, preventing false aborts in cold air.

5. **Automatic model training**: Layer 3 auto-trains if no `.joblib` files exist on startup — zero manual setup required.

6. **Dual-mode frontend**: Frontend always works standalone, auto-upgrades to live mode if backend WS connects, auto-downgrades if WS drops.
