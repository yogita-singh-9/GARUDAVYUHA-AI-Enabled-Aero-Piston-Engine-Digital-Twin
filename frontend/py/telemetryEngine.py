"""
GARUDAVYUHA – Telemetry & Physics Engine
Real-Time Physics-Coupled Telemetry Simulation for Rotax 914 Aero Piston Engine
Architecture supports live internal physics simulation and future FastAPI / CAN-Bus WebSocket bridging.
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

        # Operational State
        self.isRunning = True
        self.updateIntervalMs = 250  # 4 Hz telemetry updates
        self.intervalId = None

        # Engine Core Metrics
        self.health = 98.4  # 0 - 100%
        self.missionReadiness = 96.0  # 0 - 100%
        self.anomalyScore = 0.04  # 0.00 - 1.00
        self.predictedRUL = 48.5  # Hours
        self.missionRisk = 'LOW'  # 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
        self.activeFault = None
        self.faultProgression = 0.0  # 0.0 to 1.0
        self.faultStage = 'NORMAL'
        self.missionDurationSec = 15735  # 04:22:15 on startup

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

        # Start Simulation
        self.start()

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

        if self.dataSource == 'simulated':
            self.updatePhysicsSimulation()

        # Broadcast snapshot to listeners
        self.emit('telemetry', self.getSnapshot())

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

            if self.anomalyScore > 0.70 or self.health < 60:
                self.missionRisk = 'HIGH'
                self.missionReadiness = max(34.0, 96.0 - self.faultProgression * 58.0)
            elif self.anomalyScore > 0.35 or self.health < 80:
                self.missionRisk = 'MEDIUM'
                self.missionReadiness = max(68.0, 96.0 - self.faultProgression * 26.0)

            sub_id = self.activeFault.get("subsystemId")
            if sub_id and sub_id in self.subsystemHealth:
                sub = self.subsystemHealth[sub_id]
                base_h = float(ENGINE_SUBSYSTEMS[sub_id]["baselineHealth"])
                sub["health"] = max(18.0, base_h - (self.faultProgression * 72.0))
                sub["anomalyScore"] = self.anomalyScore
                sub["activeFault"] = self.activeFault
                if self.faultStage == 'CRITICAL':
                    sub["status"] = 'critical'
                elif self.faultStage in ('WARNING', 'AI_DETECTION'):
                    sub["status"] = 'degrading'
        else:
            self.faultStage = 'NORMAL'
            self.faultProgression = 0.0
            self.anomalyScore = max(0.03, self.anomalyScore - dt * 0.08)
            self.health = min(98.4, self.health + dt * 1.5)
            self.predictedRUL = min(48.5, self.predictedRUL + dt * 0.8)
            self.missionRisk = 'LOW'
            self.missionReadiness = min(96.0, self.missionReadiness + dt * 1.2)

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

        # Approach targets with smoothing and noise
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

    def triggerFault(self, scenario_id):
        scenario = FAULT_SCENARIOS.get(scenario_id)
        if not scenario:
            print(f"[GARUDAVYUHA] Unknown fault scenario: {scenario_id}")
            return

        self.activeFault = scenario
        self.faultProgression = 0.05
        self.faultStage = 'SUBTLE'
        self.emit('fault_triggered', {
            "scenario": scenario,
            "timestamp": self.missionDurationSec,
        })

    def setDemoStep(self, step_index):
        if step_index == 1:
            self.resetToHealthy()
            return

        self.activeFault = FAULT_SCENARIOS.get("injector_abnormality")
        progression_map = {
            1: 0.00,
            2: 0.12,
            3: 0.28,
            4: 0.40,
            5: 0.52,
            6: 0.65,
            7: 0.78,
            8: 0.92,
            9: 0.98,
            10: 1.00,
            11: 1.00,
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
        self.missionRisk = 'LOW'
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

    def getSnapshot(self):
        dynamic_cht_thresh = self.calculateDynamicThreshold('cht', ENVIRONMENT_CONFIG.get('currentAmbientTempC', 42.0), ENVIRONMENT_CONFIG.get('alphaThermalCorrection', 1.0))
        return {
            "timestamp": self.missionDurationSec,
            "formattedDuration": self.getFormattedDuration(),
            "health": round(self.health, 1),
            "missionReadiness": round(self.missionReadiness, 1),
            "anomalyScore": round(self.anomalyScore, 2),
            "predictedRUL": round(self.predictedRUL, 1),
            "rulMargin": round(self.predictedRUL * 0.12, 1),
            "missionRisk": self.missionRisk,
            "activeFault": self.activeFault,
            "faultStage": self.faultStage,
            "faultProgression": self.faultProgression,
            "sensors": dict(self.currentSensors),
            "history": {k: list(v) for k, v in self.sensorHistory.items()},
            "subsystems": {k: dict(v) for k, v in self.subsystemHealth.items()},
            "dynamicThresholds": {
                "cht": round(dynamic_cht_thresh, 1),
                "staticChtMax": SENSOR_DEFINITIONS["cht"]["normalMax"],
            },
            "samplingHz": ENVIRONMENT_CONFIG.get("telemetrySamplingHz", 500.0),
            "dataSource": self.dataSource,
        }

    def getFormattedDuration(self):
        total_sec = int(self.missionDurationSec)
        hrs = f"{total_sec // 3600:02d}"
        mins = f"{(total_sec % 3600) // 60:02d}"
        secs = f"{total_sec % 60:02d}"
        return f"{hrs}:{mins}:{secs}"

    def connectWebSocket(self, url="ws://localhost:8000/api/telemetry/ws"):
        if not IN_BROWSER or not window:
            return
        try:
            print(f"[GARUDAVYUHA] Attempting WebSocket telemetry uplink: {url}")
            WebSocket = getattr(window, 'WebSocket', None)
            if WebSocket:
                self.wsConnection = WebSocket.new(url)

                def on_open(event):
                    print("[GARUDAVYUHA] Connected to live backend telemetry feed.")
                    self.dataSource = 'websocket'
                    self.emit('connection_status', {"status": "ONLINE", "url": url})

                def on_message(event):
                    try:
                        import json
                        payload = json.loads(event.data)
                        self.applyExternalTelemetry(payload)
                    except Exception as err:
                        print("[GARUDAVYUHA] Failed to parse backend packet:", err)

                def on_close(event):
                    print("[GARUDAVYUHA] WebSocket feed closed. Reverting to internal physics simulation.")
                    self.dataSource = 'simulated'
                    self.emit('connection_status', {"status": "SIMULATED", "url": url})

                self.wsConnection.onopen = on_open
                self.wsConnection.onmessage = on_message
                self.wsConnection.onclose = on_close
        except Exception as e:
            print(f"[GARUDAVYUHA] WebSocket unavailable ({e}), operating in simulation mode.")
            self.dataSource = 'simulated'

    def applyExternalTelemetry(self, payload):
        if "sensors" in payload and isinstance(payload["sensors"], dict):
            for k, v in payload["sensors"].items():
                if k in self.currentSensors:
                    self.currentSensors[k] = v
                    self.sensorHistory[k].append(v)
                    if len(self.sensorHistory[k]) > self.historyMaxLength:
                        self.sensorHistory[k].pop(0)

        if "health" in payload:
            self.health = float(payload["health"])
        if "anomalyScore" in payload:
            self.anomalyScore = float(payload["anomalyScore"])
        if "predictedRUL" in payload:
            self.predictedRUL = float(payload["predictedRUL"])
        if "missionRisk" in payload:
            self.missionRisk = payload["missionRisk"]

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


telemetryEngine = TelemetryEngine()

if __name__ == "__main__":
    print("Running TelemetryEngine headless test...")
    telemetryEngine.tick()
    snap = telemetryEngine.getSnapshot()
    print(f"Duration: {snap['formattedDuration']}, Health: {snap['health']}%, RPM: {snap['sensors']['rpm']:.1f}")
    telemetryEngine.triggerFault("injector_abnormality")
    telemetryEngine.tick()
    snap = telemetryEngine.getSnapshot()
    print(f"Fault Active: {snap['activeFault']['name']}, Progression: {snap['faultProgression']}, Stage: {snap['faultStage']}")
    print("TelemetryEngine headless test passed!")
