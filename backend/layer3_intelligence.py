"""
layer3_intelligence.py
=======================
LAYER 3: AI/ML Diagnostic Engine (male_uav_digital_twin)

Implements the "3,700x faster" O(log N) Isolation Forest anomaly detector
described in Feasibility1.pdf Section 3, plus a Weibull/NASA-C-MAPSS RUL
model (Section 4) and a lightweight parameter-attribution ("XAI") layer that
explains *why* the anomaly score moved, in the spirit of the AI Diagnostics
tab shown in the reference UI.

Two ways to use this file:

  1. As a library: `from layer3_intelligence import AdvancedDiagnosticEngine`
     (this is what Layer 2 does).
  2. As a CLI trainer:  `python layer3_intelligence.py --train`
     - Step 1: runs the Layer 1 physics core in "standard mode" for the
       configured number of seconds (default 180s -> 360 rows at 0.5s/row,
       matching the execution blueprint exactly) to capture a HEALTHY
       baseline.
     - Step 2: fits IsolationForest(contamination=0.01) on that baseline and
       saves both the model and the feature scaler via joblib.
"""
from __future__ import annotations
import argparse
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from engine_model import (
    load_config, active_engine_params, step_state, compute_packet, residual_features,
    isolation_forest_avg_path_length, rul_from_weibull, dynamic_thermal_limit,
)

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "iforest_model.joblib")
SCALER_PATH = os.path.join(HERE, "feature_scaler.joblib")
BASELINE_MEAN_PATH = os.path.join(HERE, "baseline_stats.joblib")

FEATURES = ["rpm", "cht", "egt", "fuel_flow", "oil_pressure", "vibration"]
RESID_COLS = [f"{f}_resid" for f in FEATURES]


def generate_baseline_dataset(seconds: int, out_csv: str | None = None) -> pd.DataFrame:
    """Generates a HEALTHY baseline spanning the full operational envelope
    (ambient -10..50C, altitude 0..22000ft) AND the full engine lifespan
    (0..1.15x the Weibull scale, so ordinary wear/aging is represented too),
    with NO injected faults. For each row we store both the raw telemetry
    and its physics-corrected RESIDUAL (actual - expected-for-these-exact-
    conditions-and-flight-hours). The residual columns are what the
    Isolation Forest actually trains on - see AdvancedDiagnosticEngine below
    - so environment and normal aging are already explained away and the
    model only has to learn the tight distribution of sensor noise, which is
    far more sample-efficient and environment-invariant than learning the
    full raw joint manifold (the earlier approach, which produced false
    alarms on nominal hot-desert/cold-altitude readings)."""
    cfg = load_config()
    meta = active_engine_params(cfg)
    n_rows = int(seconds / cfg["sampling"]["physics_loop_seconds"])

    rng = np.random.default_rng(42)
    rows = []
    for _ in range(n_rows):
        ambient_temp = float(rng.uniform(-10, 50))
        altitude_ft = float(rng.uniform(0, 22000))
        flight_hours = float(rng.uniform(0, meta["weibull_scale"] * 1.15))
        packet = compute_packet(ambient_temp, altitude_ft, flight_hours, meta,
                                 fault=None, rng=rng)
        resid = residual_features(packet, meta)
        for f, v in resid.items():
            packet[f"{f}_resid"] = v
        rows.append(packet)

    df = pd.DataFrame(rows)
    if out_csv:
        df.to_csv(out_csv, index=False)
    return df


class AdvancedDiagnosticEngine:
    """Loaded once by Layer 2 and reused for every incoming telemetry packet."""

    def __init__(self, auto_train_if_missing: bool = True):
        self.cfg = load_config()
        self.meta = active_engine_params(self.cfg)
        self.history: list[dict] = []
        self.max_history = 2000
        self._ema_score: float | None = None

        if not (os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH)):
            if auto_train_if_missing:
                print("[LAYER 3] No trained model found - auto-training on a "
                      "fresh healthy baseline (this happens once).")
                train_and_save()
            else:
                raise FileNotFoundError(
                    "Model not found. Run `python layer3_intelligence.py --train` first."
                )

        self.model: IsolationForest = joblib.load(MODEL_PATH)
        self.scaler: StandardScaler = joblib.load(SCALER_PATH)
        self.baseline_stats: dict = joblib.load(BASELINE_MEAN_PATH)

    # -- core scoring -----------------------------------------------------
    def evaluate_packet(self, packet: dict) -> dict:
        resid = residual_features(packet, self.meta)
        x = np.array([[resid[f] for f in FEATURES]])
        x_scaled = self.scaler.transform(x)

        decision = self.model.decision_function(x_scaled)[0]    # higher = more normal
        anomaly_flag = bool(self.model.predict(x_scaled)[0] == -1)
        # Calibrate against the BASELINE's own decision_function distribution
        # (captured at train time) rather than assuming score_samples is
        # centred near 0 - it isn't, which previously saturated every
        # reading (healthy or not) to anomaly_score ~= 1.0.
        p50 = self.baseline_stats["decision_p50"]
        p1 = self.baseline_stats["decision_p1"]
        spread = max(p50 - p1, 1e-6)
        instant_score = float(np.clip((p50 - decision) / spread, 0.0, 1.0))
        # Exponential moving average smooths single-tick sensor noise so the
        # dashboard's Neural Anomaly Score reads like a stable diagnostic
        # trend rather than jittering with every 500ms packet.
        self._ema_score = (0.3 * instant_score + 0.7 * self._ema_score
                            if self._ema_score is not None else instant_score)
        anomaly_score = self._ema_score

        self.history.append(packet)
        if len(self.history) > self.max_history:
            self.history.pop(0)

        contributions = self._xai_contributions(resid)
        top_feature, top_z = contributions[0]
        fault_map = {
            "cht": "Overheat / Cooling Circuit Fault",
            "egt": "Combustion / Injector Abnormality",
            "vibration": "Bearing Wear / Mechanical Imbalance",
            "fuel_flow": "Fuel Injection & Induction Fault",
            "oil_pressure": "Lubrication System Fault",
            "rpm": "Governor / Throttle Linkage Fault",
        }
        confidence = float(np.clip(50 + abs(top_z) * 12, 50, 99))
        severity = "LOW"
        if anomaly_score > 0.66 or abs(top_z) > 3.5:
            severity = "HIGH"
        elif anomaly_score > 0.33 or abs(top_z) > 2.0:
            severity = "MEDIUM"

        rul_hours, rul_ci = rul_from_weibull(
            packet.get("flight_hours", 480.0),
            self.meta["weibull_shape"], self.meta["weibull_scale"],
        )

        dynamic_limit = dynamic_thermal_limit(self.meta, packet.get("ambient_temp", 15.0))

        return {
            "anomaly_score": round(anomaly_score, 4),
            "anomaly_flag": anomaly_flag,
            "severity": severity,
            "most_likely_fault": fault_map.get(top_feature, "Nominal Operation"),
            "confidence_pct": round(confidence, 1),
            "xai_contributions": [
                {"feature": f, "z_score": round(z, 2)} for f, z in contributions
            ],
            "rul_hours": round(rul_hours, 1),
            "rul_ci_hours": round(rul_ci, 1),
            "dynamic_thermal_limit_c": round(dynamic_limit, 1),
            "isolation_forest_avg_path_length": round(
                isolation_forest_avg_path_length(max(len(self.history), 2)), 3
            ),
        }

    def _xai_contributions(self, resid: dict) -> list[tuple[str, float]]:
        """Residuals are already environment/aging-corrected and should have
        ~zero mean in healthy operation, so we z-score them against the
        baseline's residual noise std to rank which channel moved most."""
        z_scores = []
        for f in FEATURES:
            mu = self.baseline_stats["mean"][f]
            sigma = max(self.baseline_stats["std"][f], 1e-6)
            z = (resid[f] - mu) / sigma
            z_scores.append((f, z))
        z_scores.sort(key=lambda kv: abs(kv[1]), reverse=True)
        return z_scores

    # -- Layer 6: Federated Fleet export -----------------------------------
    def export_fleet_node(self, node_id: str = "fleet_node_01") -> dict:
        """Serialises the learned thresholds into an exchangeable weights file
        (Layer 6 - Federated Fleet Management)."""
        payload = {
            "node_id": node_id,
            "engine": self.cfg["active_engine"],
            "contamination": self.cfg["isolation_forest"]["contamination"],
            "n_estimators": self.cfg["isolation_forest"]["n_estimators"],
            "baseline_mean": self.baseline_stats["mean"],
            "baseline_std": self.baseline_stats["std"],
            "weibull_shape": self.meta["weibull_shape"],
            "weibull_scale": self.meta["weibull_scale"],
            "exported_at": time.time(),
        }
        return payload


def train_and_save() -> None:
    cfg = load_config()
    seconds = cfg["baseline_dataset"]["seconds_of_healthy_flight"]
    out_csv = os.path.join(HERE, cfg["baseline_dataset"]["output_csv"])

    print(f"[LAYER 3] Step 1/2: generating {seconds}s of healthy baseline flight "
          f"({int(seconds / cfg['sampling']['physics_loop_seconds'])} rows)...")
    df = generate_baseline_dataset(seconds, out_csv=out_csv)

    print("[LAYER 3] Step 2/2: fitting IsolationForest on physics-corrected residuals...")
    X = df[RESID_COLS].values
    scaler = StandardScaler().fit(X)
    X_scaled = scaler.transform(X)

    ifo_cfg = cfg["isolation_forest"]
    model = IsolationForest(
        n_estimators=ifo_cfg["n_estimators"],
        contamination=ifo_cfg["contamination"],
        random_state=ifo_cfg["random_state"],
    ).fit(X_scaled)

    baseline_stats = {
        "mean": {f: df[f"{f}_resid"].mean() for f in FEATURES},
        "std": {f: df[f"{f}_resid"].std() for f in FEATURES},
    }
    decision = model.decision_function(X_scaled)
    baseline_stats["decision_p50"] = float(np.percentile(decision, 50))
    baseline_stats["decision_p1"] = float(np.percentile(decision, 1))

    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    joblib.dump(baseline_stats, BASELINE_MEAN_PATH)
    print(f"[LAYER 3] Saved model -> {MODEL_PATH}")
    print(f"[LAYER 3] Saved scaler -> {SCALER_PATH}")
    print(f"[LAYER 3] Saved baseline dataset -> {out_csv}")
    print("[LAYER 3] Training complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true", help="Generate baseline + train model")
    args = parser.parse_args()
    if args.train:
        train_and_save()
    else:
        print("Nothing to do. Pass --train to (re)generate the baseline dataset and model.")
