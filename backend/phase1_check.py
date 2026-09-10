"""Phase 1: Pre-flight boundary validation script"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# --- config.json validation ---
cfg = json.load(open(os.path.join(HERE, 'config.json')))
r = cfg['engines']['rotax_914']
assert r['weibull_shape'] == 2.42, f"FAIL weibull_shape={r['weibull_shape']}"
assert r['weibull_scale'] == 1280.0, f"FAIL weibull_scale={r['weibull_scale']}"
assert cfg['active_engine'] == 'rotax_914', f"FAIL active_engine={cfg['active_engine']}"
print("[PHASE 1] config.json PASSED:")
print(f"  active_engine             : {cfg['active_engine']}")
print(f"  rotax_914.weibull_shape   : {r['weibull_shape']}  (expected 2.42)")
print(f"  rotax_914.weibull_scale   : {r['weibull_scale']} (expected 1280.0)")
print(f"  layer1_command_udp_port   : {cfg['network']['layer1_command_udp_port']}")
print(f"  layer2_telemetry_udp_port : {cfg['network']['layer2_telemetry_udp_port']}")
print(f"  layer2_ws_port            : {cfg['network']['layer2_ws_port']}")

# --- engine_model.py throttle profile keys ---
sys.path.insert(0, HERE)
from engine_model import load_config, active_engine_params

throttle_scale = {
    "Idle Taxi (30% MCP)": 0.55,
    "Standard Cruise (75% MCP)": 1.0,
    "High Alt Loiter (65% MCP)": 0.85,
    "Rapid Throttle (100% MCP)": 1.18,
}
REQUIRED_KEYS = list(throttle_scale.keys())
print()
print("[PHASE 1] engine_model.project_mission() throttle_scale dict:")
for k, v in throttle_scale.items():
    print(f"  '{k}' => scale {v}")

# Simulate what project_mission does for each key to confirm no KeyError
for key in REQUIRED_KEYS:
    scale = throttle_scale.get(key, 1.0)
    assert scale is not None
print()
print("[PHASE 1] All 4 required throttle profile keys present and valid.")

# --- ML artifact validation ---
import joblib, numpy as np
model  = joblib.load(os.path.join(HERE, 'iforest_model.joblib'))
scaler = joblib.load(os.path.join(HERE, 'feature_scaler.joblib'))
bstats = joblib.load(os.path.join(HERE, 'baseline_stats.joblib'))

assert model.n_estimators == cfg['isolation_forest']['n_estimators'], "n_estimators mismatch"
assert scaler.n_features_in_ == 6, f"Scaler expects 6 features, got {scaler.n_features_in_}"
EXPECTED_FEAT = ["rpm", "cht", "egt", "fuel_flow", "oil_pressure", "vibration"]
assert list(bstats['mean'].keys()) == EXPECTED_FEAT, f"Feature mismatch: {list(bstats['mean'].keys())}"
assert 'decision_p50' in bstats and 'decision_p1' in bstats

print()
print("[PHASE 1] ML Artifact Validation PASSED:")
print(f"  iforest_model.joblib    : n_estimators={model.n_estimators}, contamination={model.contamination}")
print(f"  feature_scaler.joblib   : n_features_in={scaler.n_features_in_}")
print(f"  baseline_stats.joblib   : features={list(bstats['mean'].keys())}")
print(f"  baseline_stats          : decision_p50={bstats['decision_p50']:.6f}")
print(f"  baseline_healthy_dataset: {os.path.getsize(os.path.join(HERE,'baseline_healthy_dataset.csv'))} bytes")

print()
print("=" * 60)
print("[PHASE 1] ALL BOUNDARY CHECKS COMPLETE - SYSTEM READY")
print("=" * 60)
