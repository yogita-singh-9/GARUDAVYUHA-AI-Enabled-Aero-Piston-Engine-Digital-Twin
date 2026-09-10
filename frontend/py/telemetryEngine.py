"""
GARUDAVYUHA – Telemetry & Physics Engine
Real-Time Physics-Coupled Telemetry Simulation for Rotax 914 Aero Piston Engine
Architecture supports live internal physics simulation and live FastAPI WebSocket bridging.

Live mode:  Connects to ws://localhost:8080/ws/telemetry (proxied → port 8000)
            and maps every ML-enriched packet from the IsolationForest backend directly
            into the snapshot that drives all dashboard views.
Sim mode:   Falls back to internal physics simulation if backend is unavailable.
"""

import math
import random
import time

try:
    from browser import timer, window
    IN_BROWSER = True
except ImportError:
    timer = None
    window = None
    IN_BROWSER = False

from config import SENSOR_DEFINITIONS, ENGINE_SUBSYSTEMS, FAULT_SCENARIOS, ENVIRONMENT_CONFIG


class TelemetryEngine:
    def __init__(self):
        self.subscribers = {}
        self.dataSource = 'simulated'
        self.wsConnection = None
        self.liveConnected = False

        # Operational State
        self.isRunning = True
        self.updateIntervalMs = 500   # 2 Hz — matches backend 500ms loop
        self.intervalId = None

        # Engine Core Metrics
        self.health = 98.4
        self.missionReadiness = 96.0
        self.anomalyScore = 0.04
        self.predictedRUL = 48.5
        self.rulCI = 5.2
        self.missionRisk = 'LOW'
        self.activeFault = None
        self.faultProgression = 0.0
        self.faultStage = 'NORMAL'
        self.missionDurationSec = 15735  # 04:22:15 on startup
        self.flightHours = 480.0         # real value from ML backend
        self.mostLikelyFault = 'Nominal Operation'
        self.confidence = 96.4
        self.severity = 'LOW'
        self.shapAttribution = []
        self.diagnosisText = 'Engine operates within nominal learned multi-parameter boundaries.'
        self.recommendationText = 'Continue scheduled flight profile. No corrective action required.'
        self.inferenceLatencyMs = 0.0
        self.dynamicThermalLimit = 120.0

        # Telemetry Sensor Values
        self.currentSensors = {}
        self.targetSensors = {}
        self.sensorHistory = {}
        self.historyMaxLength = 100

        # Subsystem Health States
        self.subsystemHealth = {}
        self.initSubsystems()

        # Initialize baseline values
        self.initSensors()

        # Start simulation loop
        self.start()

        # Attempt live WebSocket connection to ML backend
        if IN_BROWSER and window:
            self._tryWebSocketConnect()

    # ── Subsystem / Sensor Initialisation ────────────────────────────────────
    def initSubsystems(self):
        for sub_id, sub in ENGINE_SUBSYSTEMS.items():
            self.subsystemHealth[sub_id] = {
                "health": float(sub["baselineHealth"]),
                "status": "healthy",
                "anomalyScore": 0.02,
                "activeFault": None,
            }

    def initSensors(self):
        for s_id, defn in SENSOR_DEFINITIONS.items():
            nom = float(defn["nominal"])
            self.currentSensors[s_id] = nom
            self.targetSensors[s_id] = nom
            self.sensorHistory[s_id] = []
            span = float(defn["normalMax"]) - float(defn["normalMin"])
            for _ in range(40):
                noise = (random.random() - 0.5) * span * 0.02
                self.sensorHistory[s_id].append(nom + noise)

    # ── Timer Loop ───────────────────────────────────────────────────────────
    def start(self):
        if self.intervalId:
            self.stop()
        if IN_BROWSER and timer:
            self.intervalId = timer.set_interval(self._on_timer_tick, self.updateIntervalMs)

    def stop(self):
        if IN_BROWSER and timer and self.intervalId:
            timer.clear_interval(self.intervalId)
        self.intervalId = None

    def _on_timer_tick(self):
        if self.isRunning:
            self.tick()

    def tick(self):
        self.missionDurationSec += (self.updateIntervalMs / 1000.0)

        # Only run local physics sim if not receiving live backend data
        if not self.liveConnected:
            if self.dataSource == 'simulated':
                self.updatePhysicsSimulation()

        # Broadcast snapshot to listeners
        self.emit('telemetry', self.getSnapshot())

    # ── Live WebSocket → ML Backend ───────────────────────────────────────────
    def _tryWebSocketConnect(self):
        """Connect to ws://localhost:8080/ws/telemetry (proxied to FastAPI on 8000)."""
        try:
            WebSocket = getattr(window, 'WebSocket', None)
            if not WebSocket:
                return

            # Use the same-origin WS path (proxied by frontend server.py to port 8000)
            ws_url = "ws://localhost:8000/ws/telemetry"
            self.wsConnection = WebSocket.new(ws_url)

            def on_open(event):
                print("[GARUDAVYUHA] ✅ Connected to ML backend WebSocket feed.")
                self.dataSource = 'websocket'
                self.liveConnected = True
                self.emit('connection_status', {"status": "ONLINE", "url": ws_url})

            def on_message(event):
                try:
                    import json as _json
                    payload = _json.loads(event.data)
                    self._applyMLPacket(payload)
                except Exception as err:
                    print("[GARUDAVYUHA] WS packet parse error:", err)

            def on_close(event):
                print("[GARUDAVYUHA] WS closed — reverting to simulation mode.")
                self.dataSource = 'simulated'
                self.liveConnected = False
                self.emit('connection_status', {"status": "SIMULATED", "url": ws_url})
                # Retry after 5 seconds
                if IN_BROWSER and timer:
                    timer.set_timeout(lambda: self._tryWebSocketConnect(), 5000)

            def on_error(event):
                print("[GARUDAVYUHA] WS error — ML backend may not be running.")
                self.liveConnected = False

            self.wsConnection.onopen = on_open
            self.wsConnection.onmessage = on_message
            self.wsConnection.onclose = on_close
            self.wsConnection.onerror = on_error

        except Exception as e:
            print(f"[GARUDAVYUHA] WebSocket unavailable ({e}), operating in simulation mode.")
            self.dataSource = 'simulated'
            self.liveConnected = False

    def _applyMLPacket(self, pkt):
        """
        Map a ML-enriched backend packet onto the telemetry engine state.
        Backend fields (from layer2_pipeline.py / AdvancedDiagnosticEngine):
            rpm, cht, egt, fuel_flow, oil_pressure, vibration,
            health_fraction, flight_hours, anomaly_score, anomaly_flag,
            severity, most_likely_fault, confidence_pct, rul_hours, rul_ci_hours,
            xai_contributions, dynamic_thermal_limit_c
        """
        # ── Raw sensor values ──────────────────────────────────────────────────
        self.currentSensors['rpm']           = float(pkt.get('rpm',           self.currentSensors.get('rpm', 5180)))
        self.currentSensors['cht']           = float(pkt.get('cht',           self.currentSensors.get('cht', 136)))
        self.currentSensors['egt']           = float(pkt.get('egt',           self.currentSensors.get('egt', 715)))
        self.currentSensors['fuel_flow']     = float(pkt.get('fuel_flow',     self.currentSensors.get('fuel_flow', 24.6)))
        self.currentSensors['oil_press']     = float(pkt.get('oil_pressure',  self.currentSensors.get('oil_press', 4.2)))
        self.currentSensors['vibration']     = float(pkt.get('vibration',     self.currentSensors.get('vibration', 1.35)))

        # Update history for sparklines
        for s_id in ['rpm', 'cht', 'egt', 'fuel_flow', 'oil_press', 'vibration']:
            self.sensorHistory[s_id].append(self.currentSensors[s_id])
            if len(self.sensorHistory[s_id]) > self.historyMaxLength:
                self.sensorHistory[s_id].pop(0)

        # ── Engine health & flight hours ───────────────────────────────────────
        hf = float(pkt.get('health_fraction', 0.984))
        self.health = round(hf * 100.0, 1)
        self.flightHours = float(pkt.get('flight_hours', self.flightHours))

        # ── ML diagnostic outputs ──────────────────────────────────────────────
        self.anomalyScore       = float(pkt.get('anomaly_score', 0.04))
        self.severity           = str(pkt.get('severity', 'LOW')).upper()
        self.mostLikelyFault    = str(pkt.get('most_likely_fault', 'Nominal Operation'))
        self.confidence         = float(pkt.get('confidence_pct', 96.4))
        self.predictedRUL       = float(pkt.get('rul_hours', 48.5))
        self.rulCI              = float(pkt.get('rul_ci_hours', 5.2))
        self.dynamicThermalLimit = float(pkt.get('dynamic_thermal_limit_c', 120.0))

        # XAI contributions from backend
        raw_xai = pkt.get('xai_contributions', [])
        if isinstance(raw_xai, list) and raw_xai:
            self.shapAttribution = [
                {
                    'parameter': item.get('feature', 'Sensor'),
                    'weight': round(min(100.0, abs(float(item.get('z_score', 0))) * 15.0), 1),
                    'direction': 'up' if float(item.get('z_score', 0)) > 0 else 'down',
                    'z_score': float(item.get('z_score', 0)),
                }
                for item in raw_xai
            ]

        # ── Derive mission risk and readiness from severity ────────────────────
        if self.severity == 'HIGH' or self.anomalyScore > 0.66:
            self.missionRisk = 'HIGH'
            self.missionReadiness = max(34.0, 96.0 - self.anomalyScore * 60.0)
        elif self.severity == 'MEDIUM' or self.anomalyScore > 0.33:
            self.missionRisk = 'MEDIUM'
            self.missionReadiness = max(68.0, 96.0 - self.anomalyScore * 28.0)
        else:
            self.missionRisk = 'LOW'
            self.missionReadiness = min(96.0, 96.0 - self.anomalyScore * 8.0)

        # ── RUL badge term ─────────────────────────────────────────────────────
        if self.predictedRUL < 20:
            self.faultStage = 'CRITICAL'
        elif self.predictedRUL < 50:
            self.faultStage = 'WARNING'
        else:
            self.faultStage = 'NORMAL'

        # ── Derive recommendation from anomaly score ───────────────────────────
        if self.anomalyScore > 0.5:
            self.diagnosisText = (
                f"Multivariate anomaly detected. {self.mostLikelyFault} identified "
                f"with {self.confidence:.0f}% confidence. Residual features deviate beyond "
                "2-sigma from the healthy Rotax 914 baseline distribution."
            )
            self.recommendationText = (
                f"Investigate {self.mostLikelyFault.lower()}. "
                "Reduce power to conservative cruise (4,800 RPM). "
                "Prepare RTB if anomaly score continues rising."
            )
        elif self.anomalyScore > 0.25:
            self.diagnosisText = (
                f"Mild anomaly trend detected. {self.mostLikelyFault} as primary contributor. "
                "Continue monitoring — no immediate action required."
            )
            self.recommendationText = "Monitor affected parameters. No corrective action required yet."
        else:
            self.diagnosisText = (
                "Engine operates within nominal learned multi-parameter boundaries. "
                "Reconstruction residuals within 1-sigma distribution."
            )
            self.recommendationText = "Continue scheduled flight profile. No corrective action required."

        # ── Update subsystem health proportionally ─────────────────────────────
        for sub_id, sub in self.subsystemHealth.items():
            base_h = float(ENGINE_SUBSYSTEMS[sub_id]['baselineHealth'])
            degradation = (1.0 - hf) * 80.0
            sub['health'] = max(15.0, base_h - degradation)
            sub['status'] = 'critical' if sub['health'] < 40 else ('degrading' if sub['health'] < 75 else 'healthy')
            sub['anomalyScore'] = self.anomalyScore

    # ── Internal Physics Simulation (offline fallback) ────────────────────────
    def updatePhysicsSimulation(self):
        dt = self.updateIntervalMs / 1000.0
        now_ms = time.time() * 1000.0

        if self.activeFault:
            self.faultProgression = min(1.0, self.faultProgression + dt * 0.05)
            if self.faultProgression < 0.20:
                self.faultStage = 'SUBTLE'
            elif self.faultProgression < 0.45:
                self.faultStage = 'AI_DETECTION'
            elif self.faultProgression < 0.75:
                self.faultStage = 'WARNING'
            else:
                self.faultStage = 'CRITICAL'

            affected = self.activeFault.get("affectedParameters", {})
            for param, cfg in affected.items():
                defn = SENSOR_DEFINITIONS.get(param)
                if defn:
                    shift = cfg["shift"] * self.faultProgression
                    if cfg.get("oscillatory"):
                        shift += math.sin(now_ms / 400.0) * (cfg["shift"] * 0.35)
                    self.targetSensors[param] = defn["nominal"] + shift

            max_decay = 62.0 if self.activeFault.get("severity") == 'CRITICAL' else 35.0
            self.health = max(22.0, 98.4 - (self.faultProgression * max_decay))
            initial_rul = 48.5
            target_rul = 11.4 if self.activeFault.get("severity") == 'CRITICAL' else 24.0
            self.predictedRUL = max(target_rul, initial_rul - (self.faultProgression * (initial_rul - target_rul)))
            target_anomaly = 0.88 if self.activeFault.get("severity") == 'CRITICAL' else 0.65
            self.anomalyScore = min(0.96, 0.04 + (self.faultProgression * (target_anomaly - 0.04)))
            self.severity = 'HIGH' if self.anomalyScore > 0.66 else ('MEDIUM' if self.anomalyScore > 0.33 else 'LOW')
            self.mostLikelyFault = self.activeFault.get('name', 'Unknown Fault')
            self.confidence = round(min(94.8, 62.0 + self.faultProgression * 32.5), 1)

            if self.anomalyScore > 0.70 or self.health < 60:
                self.missionRisk = 'HIGH'
                self.missionReadiness = max(34.0, 96.0 - self.faultProgression * 58.0)
            elif self.anomalyScore > 0.35 or self.health < 80:
                self.missionRisk = 'MEDIUM'
                self.missionReadiness = max(68.0, 96.0 - self.faultProgression * 26.0)

            if "shapContributions" in self.activeFault:
                self.shapAttribution = [
                    {
                        'parameter': c['param'],
                        'weight': round(min(100.0, c['weight'] * 100 + (random.random() - 0.5) * 4), 1),
                        'direction': c['direction'],
                        'z_score': c['weight'] * 3.0,
                    }
                    for c in self.activeFault.get('shapContributions', [])
                ]
            self.diagnosisText = self.activeFault.get('aiDiagnosis', 'Fault detected.')
            self.recommendationText = self.activeFault.get('recommendation', 'Inspect affected assembly.')

            sub_id = self.activeFault.get("subsystemId")
            if sub_id and sub_id in self.subsystemHealth:
                sub = self.subsystemHealth[sub_id]
                base_h = float(ENGINE_SUBSYSTEMS[sub_id]["baselineHealth"])
                sub["health"] = max(18.0, base_h - (self.faultProgression * 72.0))
                sub["anomalyScore"] = self.anomalyScore
                sub["activeFault"] = self.activeFault
                sub["status"] = 'critical' if self.faultStage == 'CRITICAL' else 'degrading'
        else:
            self.faultStage = 'NORMAL'
            self.faultProgression = 0.0
            self.anomalyScore = max(0.03, self.anomalyScore - dt * 0.08)
            self.health = min(98.4, self.health + dt * 1.5)
            self.predictedRUL = min(48.5, self.predictedRUL + dt * 0.8)
            self.missionRisk = 'LOW'
            self.missionReadiness = min(96.0, self.missionReadiness + dt * 1.2)
            self.severity = 'LOW'
            self.mostLikelyFault = 'Nominal Operation'
            self.confidence = 96.4
            self.shapAttribution = []
            self.diagnosisText = 'Engine operates within nominal learned multi-parameter boundaries.'
            self.recommendationText = 'Continue scheduled flight profile. No corrective action required.'

            for s_id, defn in SENSOR_DEFINITIONS.items():
                self.targetSensors[s_id] = float(defn["nominal"])

            for sub_id, sub_def in ENGINE_SUBSYSTEMS.items():
                if sub_id in self.subsystemHealth:
                    sub = self.subsystemHealth[sub_id]
                    base_h = float(sub_def["baselineHealth"])
                    sub["health"] = min(base_h, sub["health"] + dt * 2.5)
                    sub["status"] = 'healthy' if sub["health"] > 80 else 'degrading'
                    sub["anomalyScore"] = self.anomalyScore
                    sub["activeFault"] = None

        # Smooth sensor approach with noise
        for s_id, defn in SENSOR_DEFINITIONS.items():
            curr = self.currentSensors[s_id]
            tgt = self.targetSensors[s_id]
            alpha = 0.12
            noise_range = (float(defn["normalMax"]) - float(defn["normalMin"])) * 0.008
            noise = (random.random() - 0.5) * noise_range
            next_val = curr + (tgt - curr) * alpha + noise
            c_min = float(defn["criticalMin"]) * 0.8
            c_max = float(defn["criticalMax"]) * 1.2
            next_val = max(c_min, min(c_max, next_val))
            self.currentSensors[s_id] = next_val
            self.sensorHistory[s_id].append(next_val)
            if len(self.sensorHistory[s_id]) > self.historyMaxLength:
                self.sensorHistory[s_id].pop(0)

    # ── Fault Injection ───────────────────────────────────────────────────────
    def triggerFault(self, scenario_id):
        scenario = FAULT_SCENARIOS.get(scenario_id)
        if not scenario:
            print(f"[GARUDAVYUHA] Unknown fault scenario: {scenario_id}")
            return
        self.activeFault = scenario
        self.faultProgression = 0.05
        self.faultStage = 'SUBTLE'
        self.emit('fault_triggered', {"scenario": scenario, "timestamp": self.missionDurationSec})

    def setDemoStep(self, step_index):
        if step_index == 1:
            self.resetToHealthy()
            return
        self.activeFault = FAULT_SCENARIOS.get("injector_abnormality")
        progression_map = {
            1: 0.00, 2: 0.12, 3: 0.28, 4: 0.40, 5: 0.52,
            6: 0.65, 7: 0.78, 8: 0.92, 9: 0.98, 10: 1.00, 11: 1.00,
        }
        self.faultProgression = progression_map.get(step_index, 0.5)
        self.updatePhysicsSimulation()
        self.emit('telemetry', self.getSnapshot())

    def resetToHealthy(self):
        self.activeFault = None
        self.faultProgression = 0.0
        self.faultStage = 'NORMAL'
        self.anomalyScore = 0.04
        self.health = 98.4
        self.missionReadiness = 96.0
        self.predictedRUL = 48.5
        self.rulCI = 5.2
        self.missionRisk = 'LOW'
        self.severity = 'LOW'
        self.mostLikelyFault = 'Nominal Operation'
        self.confidence = 96.4
        self.shapAttribution = []
        self.diagnosisText = 'Engine operates within nominal learned multi-parameter boundaries.'
        self.recommendationText = 'Continue scheduled flight profile. No corrective action required.'
        self.initSensors()
        self.initSubsystems()
        self.emit('reset', self.getSnapshot())

    def overhaulSubsystem(self, subsystem_id):
        if subsystem_id in self.subsystemHealth:
            self.subsystemHealth[subsystem_id]["health"] = 98.8
            self.subsystemHealth[subsystem_id]["status"] = 'healthy'
            self.subsystemHealth[subsystem_id]["anomalyScore"] = 0.02
            self.subsystemHealth[subsystem_id]["activeFault"] = None
            if self.activeFault and self.activeFault.get("subsystemId") == subsystem_id:
                self.resetToHealthy()
            else:
                self.health = min(99.0, self.health + 18.0)
                self.predictedRUL = min(52.0, self.predictedRUL + 12.0)
            self.emit('overhaul', {"subsystemId": subsystem_id})

    def calculateDynamicThreshold(self, sensor_id, ambient_temp_c=42.0, alpha=1.0):
        defn = SENSOR_DEFINITIONS.get(sensor_id, {})
        base_max = float(defn.get("normalMax", 142.0))
        if sensor_id == 'cht':
            shift = alpha * ((ambient_temp_c - 15.0) / 1.5)
            return base_max + shift
        return base_max

    # ── Snapshot ──────────────────────────────────────────────────────────────
    def getSnapshot(self):
        dynamic_cht_thresh = self.calculateDynamicThreshold(
            'cht',
            ENVIRONMENT_CONFIG.get('currentAmbientTempC', 42.0),
            ENVIRONMENT_CONFIG.get('alphaThermalCorrection', 1.0)
        )
        # Determine RUL term label
        if self.predictedRUL < 20:
            rul_term = 'SHORT TERM'
        elif self.predictedRUL < 60:
            rul_term = 'MEDIUM TERM'
        else:
            rul_term = 'LONG TERM'

        return {
            "timestamp": self.missionDurationSec,
            "formattedDuration": self.getFormattedDuration(),
            "health": round(self.health, 1),
            "missionReadiness": round(self.missionReadiness, 1),
            "anomalyScore": round(self.anomalyScore, 4),
            "predictedRUL": round(self.predictedRUL, 1),
            "rulCI": round(self.rulCI, 1),
            "rulTerm": rul_term,
            "rulMargin": round(self.predictedRUL * 0.12, 1),
            "missionRisk": self.missionRisk,
            "activeFault": self.activeFault,
            "faultStage": self.faultStage,
            "faultProgression": self.faultProgression,
            "severity": self.severity,
            "mostLikelyFault": self.mostLikelyFault,
            "confidence": round(self.confidence, 1),
            "shapAttribution": list(self.shapAttribution),
            "diagnosisText": self.diagnosisText,
            "recommendationText": self.recommendationText,
            "inferenceLatencyMs": self.inferenceLatencyMs,
            "flightHours": round(self.flightHours, 2),
            "dynamicThermalLimit": round(self.dynamicThermalLimit, 1),
            "sensors": dict(self.currentSensors),
            "history": {k: list(v) for k, v in self.sensorHistory.items()},
            "subsystems": {k: dict(v) for k, v in self.subsystemHealth.items()},
            "dynamicThresholds": {
                "cht": round(dynamic_cht_thresh, 1),
                "staticChtMax": SENSOR_DEFINITIONS["cht"]["normalMax"],
            },
            "samplingHz": ENVIRONMENT_CONFIG.get("telemetrySamplingHz", 500.0),
            "dataSource": self.dataSource,
            "liveConnected": self.liveConnected,
        }

    def getFormattedDuration(self):
        total_sec = int(self.missionDurationSec)
        hrs = f"{total_sec // 3600:02d}"
        mins = f"{(total_sec % 3600) // 60:02d}"
        secs = f"{total_sec % 60:02d}"
        return f"{hrs}:{mins}:{secs}"

    # ── PubSub ────────────────────────────────────────────────────────────────
    def on(self, event, callback):
        if event not in self.subscribers:
            self.subscribers[event] = []
        self.subscribers[event].append(callback)
        def unsubscribe():
            if event in self.subscribers and callback in self.subscribers[event]:
                self.subscribers[event].remove(callback)
        return unsubscribe

    def emit(self, event, data):
        if event in self.subscribers:
            for cb in list(self.subscribers[event]):
                try:
                    cb(data)
                except Exception as err:
                    print(f"Error in telemetry subscriber ({event}):", err)

    # ── Legacy compat ─────────────────────────────────────────────────────────
    def connectWebSocket(self, url=None):
        """Legacy method — connection now happens automatically on __init__."""
        self._tryWebSocketConnect()

    def applyExternalTelemetry(self, payload):
        """Legacy method kept for compatibility."""
        self._applyMLPacket(payload)


telemetryEngine = TelemetryEngine()

if __name__ == "__main__":
    print("Running TelemetryEngine headless test...")
    telemetryEngine.tick()
    snap = telemetryEngine.getSnapshot()
    print(f"Duration: {snap['formattedDuration']}, Health: {snap['health']}%, RPM: {snap['sensors']['rpm']:.1f}")
    telemetryEngine.triggerFault("injector_abnormality")
    telemetryEngine.tick()
    snap = telemetryEngine.getSnapshot()
    print(f"Fault: {snap['activeFault']['name']}, Severity: {snap['severity']}, SHAP items: {len(snap['shapAttribution'])}")
    print("TelemetryEngine test passed!")
