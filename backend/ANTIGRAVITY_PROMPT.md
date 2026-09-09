Read every file in this workspace (`male_uav_digital_twin/`) end to end —
`engine_model.py`, `config.json`, `layer1_physics.py`, `layer2_pipeline.py`,
`layer3_intelligence.py`, `layer4_dashboard.py`, `convert_gltf.py`,
`requirements.txt`, `.streamlit/config.toml`, and `README.md` — before
changing anything. This is a rebuilt, integrated version of our GARUDAVYUHA
MALE UAV Digital Twin (SIH26054); README.md documents the specific bugs that
were already found and fixed (telemetry-bus threading, missing dependency,
UDP port mismatch, and four separate dataset/ML-correctness bugs in the
physics and anomaly-detection model). Do not re-introduce any of them.

Your job now is to make this run cleanly, end to end, on THIS machine, and
to reconcile it with our actual GrabCAD assets:

1. **Environment**: create/activate the venv, `pip install -r
   requirements.txt`, and fix any version conflicts you hit for this Python
   interpreter. Confirm `pygltflib`, `websocket-client`, `fastapi`,
   `uvicorn[standard]`, and `streamlit` all import cleanly.

2. **3D asset pipeline**: our real GrabCAD Rotax 914 export (`.gltf` + `.bin`
   + textures) is in `assets/`. Run `convert_gltf.py` against it, confirm
   `assets/engine_block.glb` is produced, and confirm `layer4_dashboard.py`'s
   `load_glb_base64` / `model_viewer_html` actually renders it (not the "no
   engine_block.glb found" placeholder). If the GLTF references external
   textures that don't embed cleanly into the GLB, fix `convert_gltf.py`
   (e.g. handle embedded vs. external buffers) rather than papering over it
   in the dashboard.

3. **Full 3-process integration test**: start Layer 1
   (`python layer1_physics.py`), Layer 2 (`uvicorn layer2_pipeline:app
   --host 0.0.0.0 --port 8000`), and Layer 4 (`streamlit run
   layer4_dashboard.py`), in that order. Confirm:
   - Layer 2's console shows the UDP intake bind message and no HMAC
     signature-rejection events.
   - `curl http://localhost:8000/api/latest` returns a real telemetry+
     diagnostics packet within a couple of seconds, and `/api/health` shows
     `connected_clients >= 1` once the dashboard is open.
   - The dashboard's top-right status badge reaches **LIVE** (not
     OFFLINE) within a few seconds of loading, and the Command Center's
     sensor panel and sparklines populate with real, changing values instead
     of dashes.
   - The Mission Simulator tab's "Send Scenario to Layer 1 (Live)" button
     visibly changes Layer 1's console output and the live CHT/EGT values a
     couple of seconds later (proves the reverse UDP command channel works).
   - Fix whatever breaks in this chain rather than mocking around it — if
     you find another integration bug of the same *class* as the ones in
     README.md (mismatched ports, a value one layer produces that another
     layer expects under a different key/shape, a singleton that isn't
     actually a singleton), fix it at the root and add a one-line note to
     README.md's "What was fixed" list describing it the same way the
     existing entries are written.

4. **Dataset/ML sanity re-check**: run `python layer3_intelligence.py
   --train`, then run the validation snippet at the bottom of README.md.
   Confirm the hot-desert healthy scenario reports LOW severity (this is the
   core claim of Feasibility1.pdf Section 2 — an adaptive limit should NOT
   false-alarm on environmental heat). Also manually inject an overheat
   fault (`{"fault": "overheat"}` UDP packet to Layer 1's command port, or
   equivalent) and confirm it now reports HIGH severity with the correct
   fault label. If either check fails, the bug is in `engine_model.py` or
   `layer3_intelligence.py`'s residual/calibration logic — inspect
   `baseline_healthy_dataset.csv` and the stored `decision_p1`/`decision_p50`
   percentiles to find where the distribution assumption broke, rather than
   just retraining and hoping.

5. **UI fidelity check**: compare the running dashboard tab-by-tab against
   the reference screen recording (Command Center, 3D Digital Twin, AI
   Diagnostics, RUL & Health, Mission Simulator, Mission Replay, Maintenance
   Center). Fix any visual regression — wrong colors (should be the
   BG_DARK/CYAN/GREEN/YELLOW/RED/MUTED palette already defined at the top of
   `layer4_dashboard.py`), broken card layout, or a tab that errors out
   instead of rendering — by editing the CSS/layout in `layer4_dashboard.py`,
   not by changing the underlying data contract those layers already agree
   on.

6. **Final report**: once everything above passes, give me a short summary
   of exactly what you changed (if anything) and confirm the three-process
   stack runs clean end-to-end with no errors in any of the three consoles
   and zero unresolved Problems in the IDE.

Do not change the tech stack (FastAPI + Streamlit + scikit-learn
IsolationForest + Plotly + model-viewer) — the goal is a fully working,
fully integrated version of exactly this architecture, not a rewrite in a
different stack.
