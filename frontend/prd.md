# Product Requirements Document (PRD)
## GARUDAVYUHA — Physics-Informed Digital Twin & Prognostics GCS for UAV Propulsion Health
**Problem Statement:** SIH26054
**Version:** 1.0
**Status:** Draft — Frontend Complete, Backend/ML Integration Pending

---

## 1. Overview

GARUDAVYUHA is a Ground Control Station (GCS) digital-twin platform that monitors the health of a UAV's aero-piston propulsion system (Rotax 914 proxy engine), detects anomalies in real time, and predicts Remaining Useful Life (RUL) using a physics-informed, unsupervised machine-learning pipeline. The system replaces static, threshold-based fault detection (which produces false alarms under environmental extremes such as desert heat) with an adaptive, data-driven approach validated against NASA's C-MAPSS turbofan degradation dataset.

The **frontend (GCS HMI)** already exists — a 7-view, dark-mode tactical dashboard built with Brython + Three.js + Chart.js, documented in `FRONTEND_ARCHITECTURE.md`. This PRD defines the requirements for the **data, physics-simulation, and AI/ML backend layers** that must be built to drive that existing UI, and formalizes how the provided NASA C-MAPSS run-to-failure datasets (FD001–FD004) will be used to train, validate, and benchmark the RUL/anomaly-detection engine prior to (and alongside) the live Rotax 914 physics simulator.

---

## 2. Problem Statement & Motivation

Legacy UAV propulsion monitoring uses fixed thermal/vibration thresholds (e.g., Rotax 914 coolant limit of 120°C). These thresholds do not account for environmental conditions:

- In a 45°C desert environment, natural heat-rejection loss raises equilibrium engine temperature by ~15°C (107°C nominal → 122°C), which **exceeds** the static 120°C limit and triggers a **false mission abort**, even though the engine is mechanically healthy.
- Linear wear models (`y = mx + c`) fail to capture the "knee of the curve" — the rapid, accelerating deterioration phase common to real mechanical and thermal degradation, which is exponential in nature.
- Raw multi-sensor telemetry streamed at high frequency (~32 kbps for 50 sensors at 10 Hz) saturates constrained military/UAV RF links (<5 kbps).

GARUDAVYUHA addresses these with:
1. An **adaptive, physics-derived dynamic threshold** (Ideal Gas Law–based Z-score correction) instead of a static limit.
2. An **unsupervised Isolation Forest** anomaly detector (O(log N)) replacing sequential linear threshold checks (O(N)).
3. An **exponential degradation / RUL model**, consistent with the NASA C-MAPSS damage-propagation formulation, replacing linear extrapolation.
4. **Differential (delta-vector) telemetry compression** to fit within RF bandwidth limits.

---

## 3. Goals & Success Metrics

| Metric | Legacy (Static) | Target (GARUDAVYUHA) | Basis |
|---|---|---|---|
| False Alarm Rate (high-temp ops) | ~12.5% | < 0.8% | Physics-corrected Z-score threshold |
| Fault Detection Latency | 45–90 sec | ≤ ~12 ms (edge inference) | Isolation Forest O(log N) vs O(N) scan |
| RUL Prediction Error | ± 40 hrs (linear) | ± 6 hrs (exponential) | NASA C-MAPSS decay model fit |
| Telemetry Bandwidth | ~32 kbps (raw) | ~1.5 kbps (delta) | Differential state transmission |
| Sampling Rate vs Nyquist | N/A | 500 Hz (> 2× 96.6 Hz vibration freq @ 5800 RPM) | Nyquist–Shannon compliance |

**Non-functional goal:** the system must be "engine-agnostic" — parameters (thermal base limits, wear-rate β, cylinder/vibration constants) live in a `config.json`, so the same codebase can later target the indigenous DRDO Tapas (VRDE) engine without a rewrite.

---

## 4. Existing Assets

### 4.1 Frontend (Complete — see `FRONTEND_ARCHITECTURE.md`)
A 7-section GCS dashboard is already implemented:

1. **Command Center** — mission overview, circular SVG engine-health ring, 3D twin viewport, 3×3 live sensor grid (RPM, CHT, EGT, OIL PRESS, OIL TEMP, FUEL FLOW, VIBRATION, BATTERY VOLT, INJECTION TIMING), 5 sparkline graphs, event timeline, AI diagnostics summary.
2. **Dedicated 3D Digital Twin** — fullscreen Three.js/WebGL Rotax 914 GLB model viewport.
3. **AI Diagnostics & XAI** — anomaly score readout, ML pipeline status (Bi-LSTM Autoencoder / Isolation Forest / XGBoost indicators), SHAP attribution bars, natural-language advisory.
4. **RUL & Health Analytics** — Weibull hazard metrics (β, η), degradation trajectory chart, per-subsystem health/priority table.
5. **Mission Simulator** — sliders for altitude, ambient temp, duration, throttle profile; scenario presets; forecast canvas.
6. **Black-Box Mission Replay** — playback controls, scrubbable timeline, synchronized 3D mount.
7. **Maintenance Center** — auto-generated work orders, virtual overhaul action, printable summary.

All views consume telemetry/inference data via a Python (Brython) app layer (`py/app.py`, `py/telemetryEngine.py`, `py/digitalTwin3D.py`) that expects JSON-shaped packets over the wire. **This PRD's backend layers must emit data in the shape this frontend already expects** — no frontend rework is in scope.

### 4.2 Reference Documents
- `give_execution_plan_with_each_layer.pdf` — 6-layer execution plan and team assignment.
- `Feasibility1.pdf` — mathematical feasibility proofs (thermal, computational, prognostic, signal/Nyquist, scalability).
- `so_refer_to_ps_and_all_above_chats...pdf` — finalized technology-stack matrix.
- `Damage_Propagation_Modeling.pdf` (Saxena et al., PHM'08) — the theoretical basis for the C-MAPSS dataset and the exponential health-index model this project's RUL engine is built on.

---

## 5. Dataset: NASA C-MAPSS Turbofan Degradation (Provided)

The provided data is the public **NASA Prognostics Data Repository — Turbofan Engine Degradation Simulation (C-MAPSS)** set, generated per Saxena et al. (PHM'08), and will serve as the **primary offline training/validation corpus** for Layer 3 (AI/ML Diagnostic Engine) before/alongside the live Rotax 914 physics simulator (Layer 1), since real UAV run-to-failure data is unavailable.

### 5.1 Sub-datasets

| Set | Train Units | Test Units | Operating Conditions | Fault Modes |
|---|---|---|---|---|
| FD001 | 100 | 100 | 1 (Sea Level) | 1 (HPC Degradation) |
| FD002 | 260 | 259 | 6 | 1 (HPC Degradation) |
| FD003 | 100 | 100 | 1 (Sea Level) | 2 (HPC + Fan Degradation) |
| FD004 | 248 | 249 | 6 | 2 (HPC + Fan Degradation) |

Verified row counts in the uploaded files: `train_FD001` 20,631 rows / 100 units, `train_FD002` 53,759 rows / 260 units, `train_FD003` 24,720 rows / 100 units, `train_FD004` 61,249 rows / 249 units; `test_FD00x` and `RUL_FD00x` (ground-truth remaining-cycle vectors) files are present and row-aligned per unit.

### 5.2 Schema (26 columns, space-delimited, no header)
1. Unit number
2. Time (cycles)
3–5. Operational settings 1–3 (altitude, Mach, TRA — throttle resolver angle)
6–26. Sensor measurements 1–21 (of 21 used from the 58-variable C-MAPSS model: T2, T24, T30, T50, P2, P15, P30, Nf, Nc, epr, Ps30, phi, NRf, NRc, BPR, farB, htBleed, Nf_dmd, PCNfR_dmd, W31, W32)

### 5.3 Ground truth
`RUL_FD00x.txt` — one integer per test unit = true remaining cycles at the point the test trajectory was truncated. Test RULs (FD001–003) range ~6–150 cycles.

### 5.4 How the dataset is used in this project

| Use | Layer | Purpose |
|---|---|---|
| Train Isolation Forest baseline | Layer 3 | Fit "healthy" multivariate envelope on early-life cycles (health index ≈ 1) from FD001 before switching to Rotax-simulated healthy baseline. |
| Fit exponential health-index model `h(t) = 1 − exp(a·d − b·t^c)` | Layer 3 | Validate the RUL regression approach against a known, published degradation law (Eq. 4–6 in Damage Propagation Modeling paper) before applying it to Rotax simulator output. |
| Cross-condition robustness testing | Layer 3 | FD002/FD004 (6 operating conditions) validate that the anomaly/RUL model generalizes across altitude/Mach/TRA regimes — directly mirroring the Mission Simulator's altitude/temp/duration sliders. |
| Multi-fault-mode testing | Layer 3 | FD003/FD004 (HPC + Fan degradation) validate SHAP attribution can distinguish which subsystem is degrading — feeds the AI Diagnostics view's per-parameter contribution bars. |
| RUL scoring benchmark | Layer 3 / QA | Use the asymmetric PHM'08 scoring function (Eq. 11, `a1=10`, `a2=13`, penalizing late predictions harder) as the acceptance metric for the RUL model, target ±6 hr equivalent error per the feasibility doc. |
| Sensor-to-UI mapping | Layer 2 / Frontend data contract | Map a reduced subset of the 21 C-MAPSS sensors to the frontend's 9 sensor-card fields (RPM≈Nf/Nc, EGT≈T48/T50 proxy, OIL PRESS/TEMP, VIBRATION, etc.) as stand-ins until live Rotax telemetry is available. |

**Note on scope:** the C-MAPSS engine is a large commercial turbofan (90,000 lb thrust class), not the Rotax 914 aero-piston engine. It is used here strictly as a **methodologically validated exponential run-to-failure dataset** to develop and unit-test the anomaly-detection/RUL algorithms and scoring pipeline — per the project's own "Parametric Scalability" argument (the physics/statistics are universal; only `config.json` constants change per engine).

---

## 6. System Architecture — 6-Layer Stack

| Layer | Component | Technology | Owner |
|---|---|---|---|
| 1 | Physics & Environmental Simulation Twin | Python 3.11, NumPy, SciPy | Simulator Lead + Design Lead |
| 2 | Data Ingestion & Edge Pipeline | FastAPI, Uvicorn, asyncio, WebSockets | Backend Lead |
| 3 | AI/ML Diagnostic Engine | Scikit-Learn (`IsolationForest`), Joblib | ML Lead |
| 4 | Visualization & HMI | **Existing** Brython/Three.js/Chart.js frontend (per `FRONTEND_ARCHITECTURE.md`) | Dashboard Lead + Design Lead |
| 5 | Historical Analytics & Replay | Python `csv`, Pandas | Backend Lead + Dashboard Lead |
| 6 | Federated Fleet Management | JSON config export/import | Presentation Lead |

### 6.1 Layer 1 — Physics Simulator
- Base state: 5000 RPM cruise, 115°C CHT, 820°C EGT, 1.2 g vibration.
- Air-density scaling: −25% horsepower under "High Altitude" flag.
- Baseline CHT drift: `A·e^(B·t)` as flight hours accrue (NASA decay form).
- Keyboard-triggered fault injectors (misfire, thermal spike, vibration event) for live demo.
- Emits JSON packets over WebSocket to Layer 2 at 500 Hz (satisfies Nyquist for 96.6 Hz vibration signal at 5800 RPM: `f_s > 2×96.6 = 193 Hz`).

### 6.2 Layer 2 — Ingestion/Edge Pipeline
- FastAPI app with `@app.websocket("/ws/telemetry")` endpoint and a connection-manager for multiple GCS clients.
- HMAC-SHA256 token verification per packet header (simulated military-grade link integrity).
- Routes raw packets to Layer 3, awaits anomaly/RUL vector, merges, and broadcasts final packet to the frontend.
- Implements differential/delta compression: transmit only Δ values exceeding noise threshold ε (target ≤1.5 kbps vs 32 kbps raw).
- Appends every packet to an append-only `mission_log.csv` (Layer 5 black-box recorder).

### 6.3 Layer 3 — AI/ML Diagnostic Engine
- **Baseline capture:** run Layer 1 in healthy mode (or use early-cycle C-MAPSS rows) to build a healthy reference matrix.
- **Model:** `IsolationForest(contamination=0.01)`, fit on healthy baseline, persisted via `joblib`.
- **Inference:** `evaluate_packet(data)` → feature vector → `.predict()`; a `-1` flags `Anomaly_Detected = True`.
- **RUL regression:** track slope/velocity of degrading parameters (e.g., temperature drift) and extrapolate cycles-to-threshold, informed by the exponential health-index form validated against C-MAPSS.
- **Adaptive threshold:** `Limit_dynamic = T_max + α·((T_ambient − T_std)/1.5)` (α = 1.0) replacing the static limit check.
- **Explainability:** per-parameter SHAP contribution values feed the AI Diagnostics view's attribution bars.

### 6.4 Layer 4 — Visualization (existing, integration only)
- No new UI code required. Backend must match the JSON packet schema already consumed by `py/app.py` / `py/telemetryEngine.py` (sensor values, anomaly score, confidence, RUL, SHAP bars, event-log entries, Weibull parameters β/η).

### 6.5 Layer 5 — Historical Analytics & Replay
- Append-only `mission_log.csv` writer (background thread in Layer 2).
- `st.file_uploader`-equivalent / file-picker in GCS sidebar to load a past log.
- Replay loop: `csv.DictReader` row iteration with `time.sleep(0.5)` pacing, feeding the same packet path the live stream uses so the frontend requires no branching logic.

### 6.6 Layer 6 — Fleet Management (concept/demo)
- Export trained Isolation Forest thresholds/config as `fleet_node_01.json`.
- Documented (not necessarily coded) mechanism for aggregating multiple such exports into a fleet-level model without transmitting raw telemetry — presentation/architecture artifact for the pitch.

---

## 7. Cyber-Physical & Protocol Specifications
- **Emulated data protocol:** CAN bus / SocketCAN-style JSON packaging over local WebSocket ports (stand-in for a real UAV avionics bus).
- **Security:** SHA-256 HMAC authentication tokens embedded in telemetry headers.
- **Rendering:** WebGL via `<model-viewer>` / Three.js — no heavyweight game-engine dependency.
- **Engine portability:** all physical constants (thermal base limit, wear-rate β, vibration constant) sourced from `config.json`, e.g., Rotax 914 (120°C base, β≈0.002) vs. VRDE Diesel target (95°C base, β≈0.0015).

---

## 8. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | System shall ingest simulated (Layer 1) or dataset-replayed (C-MAPSS) telemetry over WebSocket at ≥500 Hz sampling capability. |
| FR-2 | System shall compute a dynamic, environment-corrected temperature/vibration threshold per packet. |
| FR-3 | System shall run unsupervised anomaly detection on each packet and return a boolean + confidence score within edge-inference latency (~ms range). |
| FR-4 | System shall compute an estimated RUL (cycles/hours) using an exponential degradation model, updated continuously. |
| FR-5 | System shall generate SHAP-style per-parameter attribution values for any flagged anomaly. |
| FR-6 | System shall log every telemetry+inference packet to an append-only CSV for later replay. |
| FR-7 | System shall support replay of a previously logged mission at adjustable speed (1x/2x/5x/10x) through the existing Mission Replay view. |
| FR-8 | System shall export/import trained model thresholds as portable JSON config for fleet-level reuse. |
| FR-9 | System shall be validated offline against the FD001–FD004 C-MAPSS datasets using the PHM'08 asymmetric scoring function prior to acceptance. |
| FR-10 | System shall support engine-parameter swap (Rotax 914 ↔ VRDE Tapas proxy) via config change only, no code change. |

## 9. Non-Functional Requirements
- **Latency:** anomaly decision ≤ tens of ms per packet (edge-hardware feasible, O(log N)).
- **Bandwidth:** compressed telemetry stream ≤ ~1.5 kbps sustained.
- **Accuracy:** RUL mean error target ≈ ±6 (scaled hours/cycles) on held-out C-MAPSS test units, scored asymmetrically (late predictions penalized more, `a1=10`, `a2=13`).
- **Portability:** zero source-code changes required to retarget a different engine, only `config.json`.
- **Reliability:** decoupled layers so a Layer 3 (ML) fault does not crash Layer 2 (pipeline) or Layer 4 (UI).

---

## 10. Milestones (suggested)
1. Layer 1 simulator emitting valid JSON over WebSocket.
2. Layer 2 FastAPI gateway relaying Layer 1 → Layer 4 (existing frontend) end-to-end with dummy anomaly values.
3. Layer 3 Isolation Forest trained and validated offline against FD001 (single condition, single fault) — baseline accuracy check.
4. Layer 3 RUL regression validated against FD001–FD004 using the PHM'08 scoring function; iterate until within target error band.
5. Full pipeline integration: live simulator + real-time anomaly/RUL feeding all 7 existing frontend views.
6. Layer 5 black-box logging + replay wired into the existing Mission Replay view.
7. Layer 6 fleet-config export demo + presentation collateral.

## 11. Risks / Open Questions
- C-MAPSS is a turbofan model, not an aero-piston engine — sensor semantics differ from the Rotax 914; mapping must be treated as a **methodology validation**, not a literal sensor-value source, and called out as such in any demo/pitch.
- No real Rotax 914 run-to-failure data exists — Layer 1's synthetic "healthy baseline" is the actual training source for the live system; C-MAPSS is the offline algorithm-validation source only.
- SHAP computation cost vs. edge-latency budget needs benchmarking once real feature counts are finalized.
- Frontend's expected JSON packet schema should be explicitly extracted from `py/app.py`/`py/telemetryEngine.py` and documented as a formal API contract before Layer 2 implementation begins (not yet available in the uploaded files).