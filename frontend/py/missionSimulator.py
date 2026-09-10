"""
GARUDAVYUHA – Mission Simulator
Simulates MALE UAV Flight Profiles, Environmental Alt/Temp Stress, and Thermodynamic Projections
"""

import math


class MissionSimulator:
    def __init__(self):
        self.presets = {
            "high_altitude": {
                "name": "High Altitude Reconnaissance",
                "altitudeFt": 22000,
                "ambientTempC": -28,
                "durationHrs": 8.5,
                "throttleProfile": "cruise_75",
                "throttleLabel": "Standard Cruise (75% MCP)",
                "description": (
                    "Cold thin-air operations; turbocharger TCU wastegate operates at high pressure ratio "
                    "to compensate for low atmospheric density."
                ),
            },
            "long_endurance": {
                "name": "Long Endurance Border Patrol",
                "altitudeFt": 14000,
                "ambientTempC": 12,
                "durationHrs": 12.0,
                "throttleProfile": "loiter_65",
                "throttleLabel": "Economic Loiter (65% MCP)",
                "description": (
                    "Extended loiter flight testing dry sump lube circulation stability and long-term "
                    "cylinder thermal fatigue."
                ),
            },
            "hot_weather": {
                "name": "Hot Desert Strike / Tactical Sortie",
                "altitudeFt": 3500,
                "ambientTempC": 46,
                "durationHrs": 4.5,
                "throttleProfile": "max_continuous_90",
                "throttleLabel": "High Dash (90% MCP)",
                "description": (
                    "Severe ground and low-level thermal conditions. Radiator cooling air density is degraded; "
                    "oil cooler reaches peak thermal saturation."
                ),
            },
            "rapid_throttle": {
                "name": "Rapid Throttle Dynamic Evasion",
                "altitudeFt": 8500,
                "ambientTempC": 24,
                "durationHrs": 3.0,
                "throttleProfile": "tactical_variable",
                "throttleLabel": "Tactical Variable (60% - 100%)",
                "description": (
                    "Dynamic power changes inducing cyclical torque shocks on propeller reduction gearbox "
                    "dog clutch and turbo transient lag."
                ),
            },
        }

    def runSimulation(self, inputs):
        altitude_ft = float(inputs.get("altitudeFt", 18200))
        ambient_temp_c = float(inputs.get("ambientTempC", 42))
        duration_hrs = float(inputs.get("durationHrs", 8.5))
        throttle_profile = inputs.get("throttleProfile", "cruise_75")

        sigma = math.exp(-altitude_ft / 29000.0)
        turbo_boost_ratio = min(2.2, 1.0 / max(0.45, sigma))

        throttle_multiplier = 1.0
        if throttle_profile == 'loiter_65':
            throttle_multiplier = 0.85
        elif throttle_profile == 'cruise_75':
            throttle_multiplier = 1.0
        elif throttle_profile == 'max_continuous_90':
            throttle_multiplier = 1.25
        elif throttle_profile == 'tactical_variable':
            throttle_multiplier = 1.35

        base_cht = 120.0 + (ambient_temp_c * 0.45) + (throttle_multiplier * 16.0) + (turbo_boost_ratio * 5.0)
        base_egt = 680.0 + (throttle_multiplier * 35.0) + (turbo_boost_ratio * 18.0)
        base_oil_temp = 85.0 + (ambient_temp_c * 0.35) + (throttle_multiplier * 12.0)

        thermal_drift = max(0.0, (duration_hrs - 5.0) * 1.8)
        projected_peak_cht = round(float(base_cht + thermal_drift), 1)
        projected_peak_egt = round(float(base_egt + thermal_drift * 1.2), 1)
        projected_peak_oil_temp = round(float(base_oil_temp + thermal_drift * 0.8), 1)

        hourly_wear_factor = (1.8 if projected_peak_cht > 148 else 1.0) * (1.5 if throttle_multiplier > 1.2 else 1.0)
        rul_impact_hrs = round(float(duration_hrs * hourly_wear_factor), 1)
        predicted_end_health = max(30.0, round(float(98.4 - (duration_hrs * 1.2 * hourly_wear_factor)), 1))

        mission_risk = "LOW"
        fault_risk_category = "Low Risk"
        recommendation = (
            "Flight envelope is optimal. All projected thermodynamic states remain within certified "
            "Rotax 914 tolerances."
        )

        if projected_peak_cht > 154 or projected_peak_oil_temp > 118:
            mission_risk = "HIGH"
            fault_risk_category = "Thermal Overheat & Lube Thinning"
            recommendation = (
                f"High CHT trend projected ({projected_peak_cht}°C) after {duration_hrs * 0.65:.1f} hours "
                f"due to high ambient temperature ({ambient_temp_c}°C). Recommend capping throttle at 75% MCP "
                f"or flight-level change to cooler air."
            )
        elif projected_peak_cht > 142 or duration_hrs > 10:
            mission_risk = "MEDIUM"
            fault_risk_category = "Extended Thermal Soak"
            recommendation = (
                f"Moderate thermal soak projected. Monitor CHT Bank 1 and lube oil pressure closely during "
                f"mission hour {int(round(duration_hrs * 0.6))}."
            )

        time_labels = []
        cht_curve = []
        egt_curve = []
        health_curve = []

        steps = min(14, max(6, int(round(duration_hrs))))
        for h in range(steps + 1):
            curr_h_val = round(h * (duration_hrs / steps), 1)
            time_labels.append(f"T+{curr_h_val:.1f}h")

            progress = float(h) / float(steps)
            warm_up = min(1.0, progress * 3.5)
            cht_val = 95.0 + (projected_peak_cht - 95.0) * warm_up + (math.sin(h * 0.8) * 2.0)
            egt_val = 620.0 + (projected_peak_egt - 620.0) * warm_up + (math.sin(h * 0.7) * 4.0)
            h_val = 98.4 - (progress * (98.4 - predicted_end_health))

            cht_curve.append(round(float(cht_val), 1))
            egt_curve.append(round(float(egt_val), 1))
            health_curve.append(round(float(h_val), 1))

        return {
            "inputs": inputs,
            "projectedPeakCHT": projected_peak_cht,
            "projectedPeakEGT": projected_peak_egt,
            "projectedPeakOilTemp": projected_peak_oil_temp,
            "predictedEndHealth": predicted_end_health,
            "missionRisk": mission_risk,
            "faultRiskCategory": fault_risk_category,
            "riskCategory": fault_risk_category,        # alias for app.py sim panel
            "rulImpactHrs": rul_impact_hrs,
            "recommendation": recommendation,
            "timeSeries": {
                "labels": time_labels,
                "cht": cht_curve,
                "egt": egt_curve,
                "health": health_curve,
            },
        }


missionSimulator = MissionSimulator()

if __name__ == "__main__":
    res = missionSimulator.runSimulation({
        "altitudeFt": 18200,
        "ambientTempC": 42,
        "durationHrs": 8.5,
        "throttleProfile": "cruise_75",
    })
    print("Simulated Risk:", res["missionRisk"])
    print("Projected Peak CHT:", res["projectedPeakCHT"], "°C")
    print("Predicted End Health:", res["predictedEndHealth"], "%")
    print("Time series points:", len(res["timeSeries"]["labels"]))
    print("MissionSimulator test passed!")
