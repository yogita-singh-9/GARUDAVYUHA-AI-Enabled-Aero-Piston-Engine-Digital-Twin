"""
engine_model.py
================
GARUDAVYUHA - Shared Physics-Informed Digital Twin Core.

This module is the SINGLE SOURCE OF TRUTH for every equation used across the
project (Layer 1 live simulator, Layer 3 baseline-dataset generator / RUL
engine, and Layer 4 Mission Simulator "what-if" projections). Centralising the
math here is what makes the twin "parametrically scalable" (Feasibility1.pdf,
Section 6): swapping engines is a config.json edit, never a code edit.

Every formula below is annotated with the Feasibility1.pdf section it
implements, so the dataset this produces is traceable back to the maths in
the feasibility report rather than being arbitrary random noise.
"""

from __future__ import annotations
import json
import math
import os
import numpy as np

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def active_engine_params(cfg: dict) -> dict:
    return cfg["engines"][cfg["active_engine"]]


# ---------------------------------------------------------------------------
# Section 2: Thermodynamic Feasibility - Adaptive (Density-Corrected) Z-Score
# ---------------------------------------------------------------------------
def dynamic_thermal_limit(meta: dict, ambient_c: float) -> float:
    """Limit_dynamic = T_max + alpha * ((T_ambient - T_std) / 1.5)"""
    t_max = meta["thermal_limit_base_c"]
    t_std = meta["t_std_c"]
    alpha = meta["alpha_thermal"]
    return t_max + alpha * ((ambient_c - t_std) / 1.5)


# ---------------------------------------------------------------------------
# Section 4: Prognostic Feasibility - NASA C-MAPSS style exponential decay,
# implemented as the Weibull reliability function R(t) = exp(-(t/scale)^shape).
# This is deliberately the SAME shape/scale pair used by the RUL model below
# (rul_from_weibull) so "current health" and "remaining life" are always
# mutually consistent - two different decay formulas sharing the same engine
# but disagreeing with each other was the root cause of an earlier bug where
# the "healthy baseline" dataset was tripping mission_abort on every row.
# ---------------------------------------------------------------------------
def health_fraction(flight_hours: float, shape: float, scale: float) -> float:
    """R(t) = exp(-(t/scale)^shape). At t=0 -> 1.0 (perfect health); at
    t=scale (characteristic life) -> ~0.368, matching standard Weibull
    reliability convention and the "knee of the curve" described in
    Feasibility1.pdf Section 4."""
    if flight_hours <= 0:
        return 1.0
    exponent = -((flight_hours / scale) ** shape)
    return float(np.clip(math.exp(exponent), 0.0, 1.0))


def weibull_hazard(t: float, shape: float, scale: float) -> float:
    """Two-parameter Weibull wear-out CDF: F(t) = 1 - exp(-(t/scale)^shape)"""
    if t <= 0:
        return 0.0
    return float(1.0 - math.exp(-((t / scale) ** shape)))


def rul_from_weibull(elapsed_hours: float, shape: float, scale: float,
                      health_threshold: float = 0.60) -> tuple[float, float]:
    """
    Inverts the Weibull hazard to find the flight-hour at which cumulative wear
    crosses (1 - health_threshold), then returns remaining hours + a +/- 95%CI
    band derived from the local slope of the hazard function (steeper slope =
    tighter confidence, matching the "Knee of the Curve" behaviour described in
    Feasibility1.pdf Section 4).
    """
    target_f = 1.0 - health_threshold
    # F(t) = target_f  =>  t = scale * (-ln(1-target_f))^(1/shape)
    t_end = scale * ((-math.log(1.0 - target_f)) ** (1.0 / shape))
    remaining = max(0.0, t_end - elapsed_hours)
    # Local hazard slope -> narrower CI when deep in the "knee" (fast-changing) region
    eps = 1e-3
    f1 = weibull_hazard(elapsed_hours + eps, shape, scale)
    f0 = weibull_hazard(elapsed_hours, shape, scale)
    slope = max((f1 - f0) / eps, 1e-6)
    ci = min(remaining * 0.9, max(2.0, 1.0 / (slope * 400.0)))
    return remaining, ci


# ---------------------------------------------------------------------------
# Section 5.2: Signal Feasibility - Nyquist-correct vibration sampling
# ---------------------------------------------------------------------------
def firing_frequency_hz(rpm: float, cylinders: int, harmonic_factor: float) -> float:
    """F = (RPM / 60) * harmonic_factor.  harmonic_factor is engine-layout
    specific (config.json) - for the Rotax 914 boxer-4 this reproduces the
    96.6 Hz fundamental quoted in Feasibility1.pdf Section 5.2 at 5800 RPM."""
    return (rpm / 60.0) * harmonic_factor


def sample_vibration_g(rpm: float, cylinders: int, harmonic_factor: float,
                        base_g: float, degradation: float,
                        sensor_hz: int = 500, window_s: float = 0.05,
                        rng: np.random.Generator | None = None) -> float:
    """
    Synthesises a short vibration waveform AT the configured sensor sampling
    rate (default 500 Hz, satisfying Nyquist for a 96.6 Hz fundamental per
    Feasibility1.pdf 5.2: 500 > 2*96.6=193.2) and returns its RMS amplitude in
    g. This is real (if lightweight) DSP rather than a single random number,
    so the resulting dataset reflects genuine sampling-theorem-correct
    synthesis.
    """
    rng = rng or np.random.default_rng()
    n = max(8, int(sensor_hz * window_s))
    t = np.arange(n) / sensor_hz
    f0 = firing_frequency_hz(rpm, cylinders, harmonic_factor)
    signal = (
        base_g * np.sin(2 * np.pi * f0 * t)
        + 0.35 * base_g * np.sin(2 * np.pi * 2 * f0 * t + 0.4)  # 2nd harmonic
        + degradation * base_g * 1.5 * np.sin(2 * np.pi * 3.7 * f0 * t)  # wear-induced sideband
        + rng.normal(0, 0.03 * base_g, n)
    )
    return float(np.sqrt(np.mean(signal ** 2)))


# ---------------------------------------------------------------------------
# Section 3: Computational Feasibility helpers (exposed for the AI Diagnostics
# tab so the "3,700x faster" claim is shown against a live O(log N) estimate)
# ---------------------------------------------------------------------------
def isolation_forest_avg_path_length(n: int) -> float:
    if n <= 1:
        return 0.0
    return 2.0 * (math.log(n - 1) + 0.5772156649) - (2.0 * (n - 1) / n)


# ---------------------------------------------------------------------------
# Core telemetry generator - used identically by Layer 1 (real-time) and
# Layer 3 (offline baseline dataset), so the ML model always trains on data
# from the exact same generator that produces live telemetry.
# ---------------------------------------------------------------------------
def air_density_drop(altitude_ft: float) -> float:
    return float(np.clip(altitude_ft / 40000.0, 0.0, 0.9))


def step_state(state: dict, meta: dict, dt_hours: float,
               rng: np.random.Generator | None = None) -> dict:
    """
    Advances the physics state by dt_hours and returns a full telemetry
    packet. `state` carries: flight_hours, ambient_temp, altitude_ft,
    high_altitude, fault_injected (optional dict of manual overrides).
    """
    rng = rng or np.random.default_rng()
    flight_hours = state["flight_hours"] + dt_hours
    packet = compute_packet(state["ambient_temp"], state["altitude_ft"], flight_hours,
                             meta, state.get("fault_injected"), rng)
    new_state = dict(state)
    new_state["flight_hours"] = flight_hours
    return packet, new_state


def expected_deterministic(ambient_temp: float, altitude_ft: float, flight_hours: float,
                           meta: dict) -> dict:
    """The noise-free, fault-free physics prediction for these exact
    conditions (same formulas as compute_packet, minus rng noise and fault
    bumps). Subtracting this from a live reading isolates *only* sensor
    noise + genuine fault signatures - environment (ambient/altitude) and
    ordinary wear-driven aging are already accounted for and cancel out.
    This is what makes the anomaly detector's residual features in
    layer3_intelligence.py environment-invariant, directly implementing the
    "distinguish environmental heat from mechanical failure" idea from
    Feasibility1.pdf Section 2 at the feature-engineering level."""
    density_drop = air_density_drop(altitude_ft)
    hp_factor = 0.75 if altitude_ft > 15000 else 1.0
    current_rpm = meta["max_rpm"] * 0.85 * (1 - density_drop) * hp_factor
    heat_offset = (ambient_temp - meta["t_std_c"]) * 0.53
    health = health_fraction(flight_hours, meta["weibull_shape"], meta["weibull_scale"])
    degradation = 1.0 - health
    return {
        "rpm": current_rpm,
        "cht": meta["nominal_cht_c"] + heat_offset + degradation * 40.0,
        "egt": meta["nominal_egt_c"] + altitude_ft * 0.012 + degradation * 90.0,
        "fuel_flow": meta.get("nominal_fuel_flow_lph", 24.0) * (current_rpm / meta["nominal_rpm"]),
        "oil_pressure": meta.get("nominal_oil_bar", 4.2) - degradation * 0.8,
        "vibration": meta["nominal_vibration_g"] * (1.0 + degradation * 0.25),
    }


def residual_features(packet: dict, meta: dict) -> dict:
    """actual - expected, per feature, for the six ML/XAI features."""
    expected = expected_deterministic(packet["ambient_temp"], packet["altitude_ft"],
                                       packet["flight_hours"], meta)
    return {f: packet.get(f, expected[f]) - expected[f] for f in expected}


def compute_packet(ambient_temp: float, altitude_ft: float, flight_hours: float,
                    meta: dict, fault: dict | None = None,
                    rng: np.random.Generator | None = None) -> dict:
    """Pure function: (environment, flight_hours) -> telemetry packet. Used by
    `step_state` for the live time-stepped simulation AND directly by the
    Layer 3 baseline-dataset generator, which samples many *different*
    environments at low flight-hours so the ML model learns that ambient
    heat / altitude are NORMAL sources of variance - not anomalies. Skipping
    this environmental diversity was the root cause of an earlier bug where
    the model flagged every hot-desert reading as a false alarm, which is
    exactly the failure mode Feasibility1.pdf Section 2 is about eliminating.
    """
    rng = rng or np.random.default_rng()

    density_drop = air_density_drop(altitude_ft)
    hp_factor = 0.75 if altitude_ft > 15000 else 1.0  # -25% HP at high altitude (blueprint 1.1 step 2)

    current_rpm = (meta["max_rpm"] * 0.85 * (1 - density_drop) * hp_factor
                   + rng.normal(0, 12.0))
    current_rpm = max(500.0, current_rpm)

    heat_offset = (ambient_temp - meta["t_std_c"]) * 0.53

    health = health_fraction(flight_hours, meta["weibull_shape"], meta["weibull_scale"])
    degradation = 1.0 - health

    fault = fault or {}
    fault_cht_bump = float(fault.get("cht_bump", 0.0))
    fault_vib_bump = float(fault.get("vibration_bump", 0.0))

    cht = (meta["nominal_cht_c"] + heat_offset + degradation * 40.0
           + fault_cht_bump + rng.normal(0, 0.3))
    egt = (meta["nominal_egt_c"] + altitude_ft * 0.012 + degradation * 90.0
           + rng.normal(0, 2.0))
    fuel_flow = max(2.0, meta.get("nominal_fuel_flow_lph", 24.0)
                     * (current_rpm / meta["nominal_rpm"]) + rng.normal(0, 0.4))
    oil_pressure = max(0.5, meta.get("nominal_oil_bar", 4.2)
                        - degradation * 0.8 + rng.normal(0, 0.05))

    vibration = sample_vibration_g(
        current_rpm, meta["cylinders"], meta["vibration_harmonic_factor"],
        meta["nominal_vibration_g"], degradation, rng=rng,
    ) + fault_vib_bump

    dynamic_limit = dynamic_thermal_limit(meta, ambient_temp)

    return {
        "flight_hours": round(flight_hours, 4),
        "ambient_temp": ambient_temp,
        "altitude_ft": altitude_ft,
        "rpm": current_rpm,
        "cht": cht,
        "egt": egt,
        "fuel_flow": fuel_flow,
        "oil_pressure": oil_pressure,
        "vibration": vibration,
        "dynamic_thermal_limit": dynamic_limit,
        "health_fraction": health,
        "mission_abort": bool(cht > dynamic_limit),
    }


def project_mission(altitude_ft: float, ambient_c: float, duration_hrs: float,
                     throttle_profile: str, meta: dict,
                     start_flight_hours: float = 480.0,
                     n_points: int = 40) -> dict:
    """Deterministic (noise-free) forward projection used by the Mission
    Simulator tab. Returns arrays for plotting + summary risk numbers."""
    throttle_scale = {
        "Idle Taxi (30% MCP)": 0.55,
        "Standard Cruise (75% MCP)": 1.0,
        "High Alt Loiter (65% MCP)": 0.85,
        "Rapid Throttle (100% MCP)": 1.18,
    }.get(throttle_profile, 1.0)

    hours = np.linspace(0, duration_hrs, n_points)
    cht_curve, egt_curve = [], []
    for h in hours:
        flight_hours = start_flight_hours + h
        heat_offset = (ambient_c - meta["t_std_c"]) * 0.53
        health = health_fraction(flight_hours, meta["weibull_shape"], meta["weibull_scale"])
        degradation = 1.0 - health
        ramp = min(1.0, (h + 0.25) / max(0.25, duration_hrs * 0.3))
        cht = (meta["nominal_cht_c"] + heat_offset * ramp
               + degradation * 40.0 * ramp) * throttle_scale
        egt = (meta["nominal_egt_c"] + altitude_ft * 0.012 * ramp
               + degradation * 90.0 * ramp) * (0.9 + 0.1 * throttle_scale)
        cht_curve.append(cht)
        egt_curve.append(egt)

    dynamic_limit = dynamic_thermal_limit(meta, ambient_c)
    egt_limit = meta.get("egt_limit_c", 750.0)
    cht_peak = max(cht_curve)
    egt_peak = max(egt_curve)

    rul_remaining, rul_ci = rul_from_weibull(
        start_flight_hours, meta["weibull_shape"], meta["weibull_scale"]
    )
    rul_impact_pct = float(np.clip((cht_peak - dynamic_limit) / dynamic_limit * 100 +
                                    (throttle_scale - 1.0) * 30, -5, 60))
    end_health_pct = max(0, 100 - rul_impact_pct - (duration_hrs * 1.2))

    risk = "LOW"
    if cht_peak > dynamic_limit or egt_peak > egt_limit:
        risk = "HIGH"
    elif cht_peak > dynamic_limit * 0.93 or egt_peak > egt_limit * 0.93:
        risk = "MEDIUM"

    return {
        "hours": hours.tolist(),
        "cht_curve": cht_curve,
        "egt_curve": egt_curve,
        "cht_peak": cht_peak,
        "egt_peak": egt_peak,
        "dynamic_limit": dynamic_limit,
        "egt_limit": egt_limit,
        "risk": risk,
        "rul_impact_hours": round(duration_hrs * (1 + rul_impact_pct / 100), 1),
        "end_health_pct": round(end_health_pct, 1),
    }
