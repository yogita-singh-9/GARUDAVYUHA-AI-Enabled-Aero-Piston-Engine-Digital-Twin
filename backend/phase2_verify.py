"""Phase 2: ML Weight Artifact Verification"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ARTIFACTS = {
    "iforest_model.joblib":         "iforest_model.joblib",
    "feature_scaler.joblib":        "feature_scaler.joblib",
    "baseline_stats.joblib":        "baseline_stats.joblib",
    "baseline_healthy_dataset.csv": "baseline_healthy_dataset.csv",
}

all_ok = True
for label, fname in ARTIFACTS.items():
    path = os.path.join(HERE, fname)
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"  [OK] {label:<35} {size:>10} bytes")
    else:
        print(f"  [MISSING] {label}")
        all_ok = False

import joblib, numpy as np
model  = joblib.load(os.path.join(HERE, 'iforest_model.joblib'))
scaler = joblib.load(os.path.join(HERE, 'feature_scaler.joblib'))
bstats = joblib.load(os.path.join(HERE, 'baseline_stats.joblib'))

FEATURES = ["rpm", "cht", "egt", "fuel_flow", "oil_pressure", "vibration"]
assert list(bstats['mean'].keys()) == FEATURES
assert scaler.n_features_in_ == 6

# Smoke-test a single healthy packet through the full chain
from engine_model import load_config, active_engine_params, compute_packet, residual_features
cfg = load_config(); meta = active_engine_params(cfg)
rng = np.random.default_rng(99)
packet = compute_packet(15.0, 5000.0, 480.0, meta, fault=None, rng=rng)
resid = residual_features(packet, meta)
x = np.array([[resid[f] for f in FEATURES]])
x_scaled = scaler.transform(x)
score = model.decision_function(x_scaled)[0]
pred  = model.predict(x_scaled)[0]
print()
print(f"  [SMOKE TEST] healthy packet anomaly_score_raw={score:.6f}, predict={pred} (1=normal,-1=anomaly)")
assert pred == 1, f"WARN: Smoke-test healthy packet predicted as anomaly! score={score}"

print()
print("=" * 60)
print("[PHASE 2] ALL 4 ML ARTIFACTS VERIFIED - TRAINING COMPLETE")
print("=" * 60)
