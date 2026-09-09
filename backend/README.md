# GARUDAVYUHA — MALE UAV Digital Twin (SIH26054)

AI-Enhanced Engine Digital Twin for the Rotax 914 (with a config-swap path to
the indigenous DRDO TAPAS / VRDE diesel engine). This is a complete,
integrated rebuild of the 6-layer architecture from the execution blueprint,
wired to the tactical dashboard shown in the reference UI.

## What was fixed vs. the previous build

1. **Dashboard permanently stuck on "Waiting for telemetry"** — the
   background WebSocket client thread was started under `st.session_state`,
   which is not a reliable cross-rerun singleton in Streamlit. It's now a
   `@st.cache_resource` singleton (`layer4_dashboard.py`), which is the
   correct pattern for a long-lived background thread shared across reruns.
2. **Missing `pygltflib` dependency** — `convert.py` (now `convert_gltf.py`)
   imports it but it was absent from `requirements.txt`. Added.
3. **Mission Simulator → Layer 1 port mismatch** — the dashboard was sending
   scenario commands to a different UDP port than Layer 1 listened on.
   Both now read the same value from `config.json -> network`.
4. **Dataset correctness bugs** (this is the one worth reading twice):
   - The healthy baseline was generated from a single fixed environment
     (15°C / 5000ft), so the ML model treated *any* other environment as
     an anomaly — the exact false-alarm failure mode Feasibility1.pdf
     Section 2 exists to solve. Fixed by training on a diverse, randomized
     healthy envelope (-10..50°C, 0..22000ft, full engine lifespan).
   - Two independent degradation formulas (a beta/gamma exponential and a
     separate Weibull RUL model) disagreed with each other, so the
     "healthy" baseline was tripping `mission_abort=True` on every row.
     Unified into one Weibull-based health function shared by the live
     sim, the baseline generator, and the RUL predictor.
   - The thermal offset for ambient temperature was only applied when
     *hot* (`max(0, ...)`), but the dynamic safety limit is symmetric
     (it also drops in cold air) — so cold-weather readings were
     constantly (and wrongly) tripping the mission-abort threshold. Fixed
     by making the offset symmetric.
   - The IsolationForest was trained on raw sensor values, so with only
     360 samples across a wide environmental envelope, it couldn't learn
     the joint manifold and flagged genuinely nominal readings as ~100%
     anomalous. Fixed by training on **physics-corrected residuals**
     (`actual − expected-for-these-exact-conditions`), which is the
     feature-engineering equivalent of Feasibility1.pdf Section 2's whole
     argument: separate environmental variation from mechanical failure
     *before* the model ever sees the data.
   - The anomaly-score normalisation assumed `IsolationForest.score_samples`
     is centred near 0 — it isn't — which saturated every reading (healthy
     or faulty) to ~1.0. Fixed by calibrating against the baseline's own
     `decision_function` percentiles, plus an EMA smoother so the gauge
     doesn't jitter with every 500ms packet.
6. **3D Asset Pipeline external texture bug** — `convert_gltf.py` was saving binary files without embedding external buffers and textures, causing the dashboard's model-viewer to show an untextured block or fail to render. Fixed by converting buffers and images to `BINARYBLOB`/`BUFFERVIEW` format before saving.
7. **Dashboard UI color hardcoding** — The AI Diagnostics tab was rendering some text with hardcoded `#94a3b8` colors instead of using the central `MUTED` palette variable, violating the design contract. Fixed by converting the layout string to an f-string and injecting `{MUTED}`.

   All of this is verified in-repo: run `python layer3_intelligence.py --train`
   then see the validation snippet at the bottom of this file.

## Architecture

```
male_uav_digital_twin/
├── assets/                 <- put your GrabCAD GLTF export here
├── engine_model.py         <- SHARED physics core (Layers 1, 3, 4 all import this)
├── config.json             <- engine params (Rotax 914 / VRDE Tapas), ports, secrets
├── layer1_physics.py       <- Layer 1: real-time engine simulator (UDP out)
├── layer2_pipeline.py      <- Layer 2 + 5 + 6: FastAPI bus, ML enrichment, CSV logger, fleet export
├── layer3_intelligence.py  <- Layer 3: IsolationForest + Weibull RUL + XAI (library + trainer CLI)
├── layer4_dashboard.py     <- Layer 4: Streamlit tactical HMI
├── convert_gltf.py         <- GLTF -> GLB converter for the 3D viewer
├── requirements.txt
└── .streamlit/config.toml  <- forces the dark theme
```

Data flow: **Layer 1** simulates the engine and UDP-streams signed telemetry
to **Layer 2**, which verifies the signature, runs it through **Layer 3**'s
anomaly/RUL model, logs it to `mission_log.csv` (Layer 5), and broadcasts the
enriched packet over WebSocket to **Layer 4**'s dashboard. The dashboard's
Mission Simulator tab can also push a scenario back to Layer 1 over a second
UDP channel.

## Setup

```bash
cd male_uav_digital_twin
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Drop your GrabCAD Rotax 914 export (the `.gltf` + `.bin` + textures) into
`assets/`, then:

```bash
python convert_gltf.py
```

This produces `assets/engine_block.glb`, which the dashboard base64-embeds
into a `<model-viewer>` component. If you skip this step the 3D Digital Twin
tab shows a placeholder instead of crashing.

## Running (3 terminals)

```bash
# Terminal 1 - Layer 1 (physics simulator)
python layer1_physics.py

# Terminal 2 - Layer 2 (data bus + ML + CSV logger)
uvicorn layer2_pipeline:app --host 0.0.0.0 --port 8000

# Terminal 3 - Layer 4 (dashboard)
streamlit run layer4_dashboard.py
```

The first time Layer 2 starts, it auto-trains Layer 3's model if one isn't
found (equivalent to running `python layer3_intelligence.py --train`
yourself, which you can also do ahead of time to inspect
`baseline_healthy_dataset.csv`).

Open the Streamlit URL it prints (usually `http://localhost:8501`). The
Command Center should show live-updating values within ~1-2 seconds and the
top-right badge should read **LIVE**.

## Switching engines (Section 6 — parametric scalability)

Edit `config.json`:
```json
"active_engine": "vrde_tapas"
```
No code changes needed — every formula in `engine_model.py` reads engine
parameters from this file.

## Demo controls

- **Mission Simulator tab** → sliders + "Send Scenario to Layer 1 (Live)"
  pushes real ambient/altitude changes into the running simulation.
- **Fault injection**: send a UDP JSON packet to Layer 1's command port
  (`9998` by default) with `{"fault": "overheat"}`,
  `{"fault": "vibration_spike"}`, or `{"fault": "clear"}` — a small keyboard
  script wrapping this is a good addition if you want a physical demo button.
- **Mission Replay tab** reads `mission_log.csv` (or an uploaded CSV) once
  some flight time has accumulated.
- **Maintenance Center → Export Fleet Node Config** hits Layer 2's
  `/api/fleet/export` (Layer 6) and writes `fleet_node_01.json`.

## Validating the dataset yourself

```bash
python layer3_intelligence.py --train
python - <<'PY'
from layer3_intelligence import AdvancedDiagnosticEngine
from engine_model import load_config, active_engine_params, step_state
import numpy as np
engine = AdvancedDiagnosticEngine()
meta = active_engine_params(load_config())
rng = np.random.default_rng(1)
state = {"flight_hours": 80.0, "ambient_temp": 45.0, "altitude_ft": 10200.0, "fault_injected": {}}
for _ in range(10):
    packet, state = step_state(state, meta, 0.5/3600, rng=rng)
    diag = engine.evaluate_packet(packet)
print("Hot-desert healthy reading -> severity:", diag["severity"], "score:", diag["anomaly_score"])
# Expect LOW severity even though the raw CHT (~131C) is well above the
# static 120C limit — this is the whole point of Section 2's adaptive limit.
PY
```

## Known limitations / good next steps

- The XAI panel uses z-score parameter attribution (physics-corrected
  residual vs. baseline noise), not true SHAP values — it's labelled as such
  in the UI. Swapping in `shap.TreeExplainer` on the IsolationForest is a
  reasonable upgrade if you have time before judging.
- Mission Replay's playback is scrub-based, not auto-playing, to avoid
  Streamlit rerun-loop fragility. A `streamlit-autorefresh`-driven auto-play
  is a straightforward add if you want it.
- The dashboard's live refresh is a blocking `time.sleep(1); st.rerun()` at
  the end of the script — simple and dependency-free, but not as smooth as
  `streamlit-autorefresh`. Swap it in if you `pip install streamlit-autorefresh`.
