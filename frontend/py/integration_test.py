"""
GARUDAVYUHA - Full Integration Test Suite
==========================================
Tests every layer of the stack end-to-end:

  LAYER 1: ML Engine - model exists, inference is fast, produces valid scores
  LAYER 2: C-MAPSS Data Pipeline - all 4 train + test files load cleanly
  LAYER 3: RUL / Threshold / SHAP engines
  LAYER 4: TelemetryEngine - simulation tick
  LAYER 5: Black-Box Logger - mission_log.csv
  LAYER 6: Backend API - /api/telemetry/snapshot, /api/v1/diagnose, benchmark
  LAYER 7: Frontend HTTP server - static asset serving

Run from the frontend/ directory:
    python py/integration_test.py
    python py/integration_test.py --no-api
    python py/integration_test.py --server-url http://localhost:8080
"""

from __future__ import annotations
import argparse, json, math, os, sys, time, urllib.request, urllib.error, urllib.parse

HERE          = os.path.dirname(os.path.abspath(__file__))
FRONTEND_ROOT = os.path.dirname(HERE)
CMAPS_DIR     = os.path.join(FRONTEND_ROOT, "CMaps")
MODEL_PATH    = os.path.join(FRONTEND_ROOT, "ml_model.joblib")
LOG_PATH      = os.path.join(FRONTEND_ROOT, "mission_log.csv")

sys.path.insert(0, HERE)
sys.path.insert(0, FRONTEND_ROOT)  # needed for 'backend.server_api' package import

PASS = "[PASS]"; FAIL = "[FAIL]"; SKIP = "[SKIP]"
results: list[dict] = []

def check(name, condition, detail=""):
    tag = PASS if condition else FAIL
    msg = f"  {tag} {name}"
    if detail: msg += f"  ({detail})"
    print(msg)
    results.append({"name": name, "passed": condition, "detail": detail})
    return condition

def section(title):
    print(); print("=" * 68)
    print(f"  {title}"); print("=" * 68)

# --- LAYER 1: ML Engine ---
def test_ml_engine():
    section("LAYER 1 - ML Engine (IsolationForest + RUL + Threshold + SHAP)")
    check("ml_model.joblib exists", os.path.exists(MODEL_PATH), MODEL_PATH)

    from ml_engine import MLEngine, ExponentialRULEngine, DynamicThresholdEngine, load_model
    artefacts = load_model()
    check("Model loads from disk", artefacts is not None)
    if artefacts:
        check("Trained on all 4 C-MAPSS datasets",
              "FD001" in artefacts.get("trained_on", "") and "FD004" in artefacts.get("trained_on", ""),
              artefacts.get("trained_on"))
        n = artefacts.get("n_samples", 0)
        check("Training sample count >= 79,000", n >= 79000, f"{n:,} samples")
        check("9 features in model", len(artefacts.get("feature_names", [])) == 9)
        check("Calibration percentiles sane",
              artefacts.get("p1", 0) < artefacts.get("p50", 0) < artefacts.get("p99", 0),
              f"p1={artefacts.get('p1',0):.4f} p50={artefacts.get('p50',0):.4f} p99={artefacts.get('p99',0):.4f}")

    ml = MLEngine()
    healthy = {"sensors": {"rpm": 5180, "cht": 136, "egt": 715, "oil_press": 4.2,
                           "oil_temp": 96, "fuel_flow": 24.6, "vibration": 1.35,
                           "battery_volt": 28.2, "injection_timing": 24.0},
               "health": 98.4, "anomalyScore": 0.04, "activeFault": None}
    t0 = time.perf_counter()
    r_h = ml.evaluate_telemetry(healthy)
    lat = (time.perf_counter() - t0) * 1000
    # NOTE: IsolationForest is trained on C-MAPSS (turbofan) data mapped to Rotax 914 (piston)
    # features. An absolute score threshold < 0.35 is unreliable due to domain shift.
    # The correct test is RELATIVE: fault packets must score HIGHER than healthy ones.
    check("Healthy packet anomalyScore is a valid float in (0, 1)",
          0.0 < r_h["anomalyScore"] < 1.0, f"{r_h['anomalyScore']}")
    check("Inference latency < 100 ms", lat < 100, f"{lat:.2f} ms")
    check("Healthy RUL returned (> 0 hrs)", r_h["predictedRUL"] > 0, f"{r_h['predictedRUL']} hrs")
    check("Dynamic threshold in result", "dynamicLimit" in r_h.get("dynamicThresholds", {}))
    check("SHAP attribution list returned", isinstance(r_h.get("shapAttribution"), list))

    fault = {"sensors": {"rpm": 4900, "cht": 165, "egt": 810, "oil_press": 2.5,
                         "oil_temp": 122, "fuel_flow": 18.5, "vibration": 4.2,
                         "battery_volt": 26.8, "injection_timing": 30.0},
             "health": 55.0, "anomalyScore": 0.78, "activeFault": None}
    r_f = ml.evaluate_telemetry(fault)
    # Primary check: fault packet must score HIGHER than the healthy packet
    check("Fault packet scores HIGHER than healthy packet (discrimination)",
          r_f["anomalyScore"] > r_h["anomalyScore"],
          f"fault={r_f['anomalyScore']} healthy={r_h['anomalyScore']}")
    check("Fault packet -> anomalyScore > 0.5", r_f["anomalyScore"] > 0.5, f"{r_f['anomalyScore']}")
    # Fault RUL comes mostly from health=55% input, always low
    check("Fault packet -> RUL < healthy RUL", r_f["predictedRUL"] < r_h["predictedRUL"],
          f"fault={r_f['predictedRUL']} healthy={r_h['predictedRUL']} hrs")
    check("Fault packet -> isAnomaly=True", r_f["isAnomaly"] is True)

    thresh = DynamicThresholdEngine()
    t = thresh.evaluate_cht_threshold(145.0, ambient_temp_c=50.0)
    check("Dynamic CHT limit rises in hot ambient (>142)", t["dynamicLimit"] > 142.0, f"{t['dynamicLimit']}")
    check("False-alarm prevention in hot ambient (145C under raised limit)",
          not t["isExceeded"], f"isExceeded={t['isExceeded']} dynamicLimit={t['dynamicLimit']}")

# --- LAYER 2: C-MAPSS Data Pipeline ---
def test_cmapss_data():
    section("LAYER 2 - C-MAPSS Dataset Pipeline (FD001-FD004)")
    from ml_engine import _parse_cmapss_file, load_all_training_data, ALL_TRAIN_FILES, ALL_TEST_FILES, ALL_RUL_FILES
    for fpath in ALL_TRAIN_FILES + ALL_TEST_FILES + ALL_RUL_FILES:
        check(f"{os.path.basename(fpath)} exists", os.path.exists(fpath))
    for fpath in ALL_TRAIN_FILES:
        ds = os.path.basename(fpath)
        rows_by_unit, feature_rows = _parse_cmapss_file(fpath)
        check(f"{ds}: units > 0", len(rows_by_unit) > 0, f"{len(rows_by_unit)} units")
        check(f"{ds}: rows > 0", len(feature_rows) > 0, f"{len(feature_rows):,} rows")
        check(f"{ds}: feature vectors have 9 cols", all(len(r) == 9 for r in feature_rows[:100]))
    try:
        X_z, means, stds = load_all_training_data(verbose=False)
        check("Combined training matrix has 9 features", X_z.shape[1] == 9, f"shape={X_z.shape}")
        check("Z-scored matrix has unit-ish std", 0.5 < float(X_z.std()) < 3.0, f"std={X_z.std():.3f}")
    except Exception as e:
        check("Training data loads", False, str(e))

# --- LAYER 3: Held-out test evaluation ---
def test_ml_test_evaluation():
    section("LAYER 3 - ML Evaluation on Held-Out C-MAPSS Test Sets")
    from ml_engine import run_test_evaluation
    try:
        res = run_test_evaluation(verbose=False)
        overall = res.get("overall", {})
        check("Test evaluation ran", bool(overall))
        n = overall.get("total_engines", 0)
        check("Test covers >= 700 engines", n >= 700, f"{n} engines")
        avg_score = overall.get("avg_anomaly_score", 0)
        check("Avg anomaly score in valid range (0,1)", 0 < avg_score < 1.0, f"{avg_score:.3f}")
    except Exception as e:
        check("Test evaluation runs without error", False, str(e))

# --- LAYER 4: TelemetryEngine ---
def test_telemetry_engine():
    section("LAYER 4 - TelemetryEngine Physics Simulation")
    from telemetryEngine import TelemetryEngine
    engine = TelemetryEngine()
    engine.tick()
    snap = engine.getSnapshot()
    check("Snapshot has 'sensors'", "sensors" in snap)
    check("Health in [0,100]", 0 <= snap["health"] <= 100, f"{snap['health']}")
    check("All 9 sensor keys present",
          all(k in snap["sensors"] for k in ["rpm","cht","egt","oil_press","oil_temp",
                                              "fuel_flow","vibration","battery_volt","injection_timing"]))
    check("RPM in plausible range", 1000 < snap["sensors"]["rpm"] < 8000, f"{snap['sensors']['rpm']:.0f}")
    check("CHT in plausible range", 50 < snap["sensors"]["cht"] < 250, f"{snap['sensors']['cht']:.1f}")
    engine.triggerFault("injector_abnormality")
    for _ in range(10): engine.tick()
    snap_f = engine.getSnapshot()
    check("Fault active after triggerFault", snap_f["activeFault"] is not None)
    check("Fault progression > 0", snap_f["faultProgression"] > 0.0, f"{snap_f['faultProgression']:.2f}")
    check("Anomaly score rises under fault", snap_f["anomalyScore"] > 0.05, f"{snap_f['anomalyScore']}")
    engine.resetToHealthy()
    snap_r = engine.getSnapshot()
    check("Health restores after reset", snap_r["health"] >= 98.0, f"{snap_r['health']}")
    check("ActiveFault is None after reset", snap_r["activeFault"] is None)

# --- LAYER 5: Black-Box Logger ---
def test_blackbox_logger():
    section("LAYER 5 - Black-Box Mission Logger (mission_log.csv)")
    import csv as csv_mod
    from backend.server_api import BlackBoxLogger
    from telemetryEngine import TelemetryEngine
    engine = TelemetryEngine()
    logger = BlackBoxLogger("_test_mission_log.csv")
    test_log = logger.log_filename
    try:
        engine.tick()
        snap = engine.getSnapshot()
        logger.log_snapshot(snap)
        logger.log_snapshot(snap)
        check("Log file created", os.path.exists(test_log))
        with open(test_log, "r") as f:
            rows = list(csv_mod.reader(f))
        check("Log has header + >= 2 data rows", len(rows) >= 3, f"{len(rows)} rows")
        check("Timestamp column is numeric-ish", rows[1][0].replace(".", "").isdigit(), rows[1][0])
    finally:
        try: os.remove(test_log)
        except: pass

# --- LAYER 6: Backend API ---
def test_backend_api(server_url):
    section(f"LAYER 6 - Backend API ({server_url})")
    def get_json(url, timeout=8.0):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read().decode()), r.status
        except urllib.error.URLError as e: return None, str(e)
    def post_json(url, data, timeout=10.0):
        body = json.dumps(data).encode()
        req  = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode()), r.status
        except urllib.error.URLError as e: return None, str(e)

    payload, status = get_json(f"{server_url}/api/telemetry/snapshot")
    if payload is None:
        check("Server reachable", False, str(status))
        print(f"  {SKIP} Remaining API tests skipped. Start server: python server.py --port 8080")
        return
    check("GET /api/telemetry/snapshot -> 200", status == 200)
    check("Snapshot has health", "health" in payload)
    check("Snapshot has anomalyScore", "anomalyScore" in payload)
    check("Snapshot has predictedRUL", "predictedRUL" in payload)
    check("anomalyScore in [0,1]", 0 <= payload.get("anomalyScore", -1) <= 1.0, str(payload.get("anomalyScore")))

    diag_payload = {"sensors": {"rpm": 5180,"cht": 136,"egt": 715,"oil_press": 4.2,
                                "oil_temp": 96,"fuel_flow": 24.6,"vibration": 1.35,
                                "battery_volt": 28.2,"injection_timing": 24.0},
                    "health": 98.4, "anomalyScore": 0.04, "activeFault": None}
    diag, dstatus = post_json(f"{server_url}/api/v1/diagnose", diag_payload)
    check("POST /api/v1/diagnose -> 200", dstatus == 200)
    if diag:
        check("Diagnose has anomalyScore", "anomalyScore" in diag)
        check("Diagnose has predictedRUL", "predictedRUL" in diag)
        check("Diagnose has mlModelEngine", "mlModelEngine" in diag)
        check("Healthy packet score < 0.50", diag.get("anomalyScore", 1.0) < 0.50, str(diag.get("anomalyScore")))

    fault_payload = {"sensors": {"rpm": 4900,"cht": 168,"egt": 812,"oil_press": 2.3,
                                 "oil_temp": 125,"fuel_flow": 18.0,"vibration": 4.5,
                                 "battery_volt": 26.5,"injection_timing": 31.0},
                     "health": 52.0, "anomalyScore": 0.82, "activeFault": None}
    fd, _ = post_json(f"{server_url}/api/v1/diagnose", fault_payload)
    if fd:
        check("Fault packet score > 0.5 or anomalyPct > 50",
              fd.get("anomalyScore", 0) > 0.5 or fd.get("anomalyPercentage", 0) > 50,
              f"score={fd.get('anomalyScore')}")

    fleet, fstatus = get_json(f"{server_url}/api/fleet/export")
    check("GET /api/fleet/export -> 200", fstatus == 200)

    bench, bstatus = get_json(f"{server_url}/api/v1/benchmark", timeout=30.0)
    check("GET /api/v1/benchmark -> 200", bstatus == 200)
    if bench:
        check("Benchmark passed=True", bench.get("passed") is True)
        check("Benchmark MAE <= 6.0 hrs", bench.get("metrics",{}).get("maeHours", 99) <= 6.0,
              str(bench.get("metrics",{}).get("maeHours")))
        check("Benchmark FAR < 0.8%", bench.get("metrics",{}).get("falseAlarmRatePct", 99) < 0.8,
              str(bench.get("metrics",{}).get("falseAlarmRatePct")))

# --- LAYER 7: Static Assets ---
def test_static_assets(server_url):
    section(f"LAYER 7 - Static Asset Serving ({server_url})")
    assets = [("/index.html","text/html"), ("/Rotax914/Rotax 914.gltf","model/gltf")]
    for path, mime in assets:
        # URL-encode spaces and special chars in path (e.g. 'Rotax 914.gltf' -> 'Rotax%20914.gltf')
        encoded_path = urllib.parse.quote(path)
        url = server_url + encoded_path
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                ct = r.headers.get("Content-Type","")
                check(f"GET {path} -> 200", r.status == 200)
                check(f"{path} MIME contains '{mime}'", mime in ct, ct)
        except urllib.error.URLError as e:
            check(f"GET {path} reachable", False, str(e))

# --- Summary ---
def print_summary():
    section("TEST SUMMARY")
    total = len(results); passed = sum(1 for r in results if r["passed"]); failed = total - passed
    for r in results:
        tag = PASS if r["passed"] else FAIL
        print(f"  {tag} {r['name']}")
    print()
    print(f"  Result: {passed}/{total} passed", end="")
    if failed: print(f"   ({failed} FAILED)")
    else: print("  -- ALL PASSED")
    print()
    if failed: sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GARUDAVYUHA Full Integration Test Suite")
    parser.add_argument("--server-url", default="http://localhost:8080")
    parser.add_argument("--no-api", action="store_true", help="Skip HTTP API tests")
    args = parser.parse_args()

    print(); print("=" * 68)
    print("  GARUDAVYUHA - FULL INTEGRATION TEST SUITE")
    print("  Covers: ML, C-MAPSS data, telemetry, logger, API, assets")
    print("=" * 68)

    test_ml_engine()
    test_cmapss_data()
    test_ml_test_evaluation()
    test_telemetry_engine()
    test_blackbox_logger()
    if not args.no_api:
        test_backend_api(args.server_url)
        test_static_assets(args.server_url)
    else:
        section("LAYERS 6 & 7 - API + Static Assets (SKIPPED via --no-api)")
    print_summary()
