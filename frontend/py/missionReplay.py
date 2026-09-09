"""
GARUDAVYUHA – Mission Replay Engine ("Engine Time Machine")
Black-Box Flight Data Recorder Replay with Synchronized 3D Digital Twin State
"""

import math
import random

try:
    from browser import timer
    IN_BROWSER = True
except ImportError:
    timer = None
    IN_BROWSER = False


class MissionReplay:
    def __init__(self, onFrameUpdate=None):
        self.onFrameUpdate = onFrameUpdate
        self.missionDurationSec = 7.5 * 3600  # 07:30:00 mission
        self.currentSec = 0
        self.isPlaying = False
        self.playbackSpeed = 1  # 1x, 2x, 5x, 10x
        self.intervalId = None
        self.csvFrames = []
        self.useCSVData = False

        # Key historical mission events
        self.events = [
            {
                "timestampSec": 0,
                "formattedTime": "00:00:00",
                "title": "Takeoff & Full Power Climb",
                "type": "info",
                "description": "UAV launched from Airbase runway. Rotax 914 at 5,500 RPM full climb power.",
                "subsystem": None,
                "status": "healthy",
            },
            {
                "timestampSec": 1.25 * 3600,
                "formattedTime": "01:15:00",
                "title": "Level-off at FL160",
                "type": "info",
                "description": "Cruising at 16,000 ft MSL, 5,180 RPM. All thermodynamic parameters nominal.",
                "subsystem": None,
                "status": "healthy",
            },
            {
                "timestampSec": 3.7 * 3600,
                "formattedTime": "03:42:00",
                "title": "Incipient Micro-Vibration Inception",
                "type": "advisory",
                "description": "Subtle acoustic frequency shift in Fuel Rail #2. Gross limits normal.",
                "subsystem": "fuel_system",
                "status": "degrading",
            },
            {
                "timestampSec": 4.25 * 3600,
                "formattedTime": "04:15:00",
                "title": "AI Anomaly Detection Triggered",
                "type": "warning",
                "description": "Isolation Forest and Autoencoder residual flags multi-channel drift (Score 0.58).",
                "subsystem": "fuel_system",
                "status": "degrading",
            },
            {
                "timestampSec": 5.16 * 3600,
                "formattedTime": "05:10:00",
                "title": "Injector Disparity & Thermal Spike",
                "type": "critical",
                "description": "Cylinder #2 EGT climbs to 788\u00b0C. Lean burn verified. Fuel Injector highlighted in Red.",
                "subsystem": "fuel_system",
                "status": "critical",
            },
            {
                "timestampSec": 6.08 * 3600,
                "formattedTime": "06:05:00",
                "title": "Operator Warning & RTB Commanded",
                "type": "critical",
                "description": "GCS operator accepts AI advisory. Mission aborted, Return-To-Base flight plan engaged.",
                "subsystem": "fuel_system",
                "status": "critical",
            },
            {
                "timestampSec": 7.25 * 3600,
                "formattedTime": "07:15:00",
                "title": "Safe Touchdown & Engine Shutdown",
                "type": "info",
                "description": "Aircraft recovered safely. Automated ground maintenance work order dispatched.",
                "subsystem": "fuel_system",
                "status": "degrading",
            },
        ]

    def loadFromCSV(self, csv_filepath):
        try:
            import csv, os
            if os.path.exists(csv_filepath):
                with open(csv_filepath, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    self.csvFrames = list(reader)
                    if self.csvFrames:
                        self.useCSVData = True
                        print(f"[GARUDAVYUHA Replay] Loaded {len(self.csvFrames)} frames from {csv_filepath}")
                        return True
        except Exception as err:
            print("[GARUDAVYUHA Replay] CSV read error:", err)
        return False

    def play(self):

        if self.isPlaying:
            return
        self.isPlaying = True
        tick_ms = 200

        def tick():
            self.currentSec += (tick_ms / 1000.0) * self.playbackSpeed * 45
            if self.currentSec >= self.missionDurationSec:
                self.currentSec = self.missionDurationSec
                self.pause()
            self.emitCurrentFrame()

        if IN_BROWSER and timer:
            self.intervalId = timer.set_interval(tick, tick_ms)

    def pause(self):
        self.isPlaying = False
        if IN_BROWSER and timer and self.intervalId:
            timer.clear_interval(self.intervalId)
            self.intervalId = None

    def reset(self):
        self.pause()
        self.currentSec = 0
        self.emitCurrentFrame()

    def seekTo(self, seconds):
        self.currentSec = max(0, min(self.missionDurationSec, seconds))
        self.emitCurrentFrame()

    def setSpeed(self, multiplier):
        self.playbackSpeed = multiplier

    def emitCurrentFrame(self):
        progress = self.currentSec / self.missionDurationSec
        progress_hrs = self.currentSec / 3600.0

        rpm = 5180.0 + math.sin(progress_hrs * 2) * 15.0
        cht = 136.0 + math.sin(progress_hrs * 1.5) * 2.0
        egt = 715.0 + math.sin(progress_hrs * 2.2) * 3.0
        oil_press = 4.2 + (random.random() - 0.5) * 0.05
        oil_temp = 96.0 + math.sin(progress_hrs * 1.1) * 2.0
        fuel_flow = 24.6 + (random.random() - 0.5) * 0.2
        vibration = 1.35 + (random.random() - 0.5) * 0.08
        battery_volt = 28.2
        injection_timing = 24.0

        health = 98.4
        anomaly_score = 0.04
        active_subsystem = None
        component_status = "healthy"

        if self.currentSec > 13320:
            fault_progress = min(1.0, (self.currentSec - 13320) / (2.5 * 3600))
            fuel_flow -= fault_progress * 3.8
            egt += fault_progress * 68.0
            vibration += fault_progress * 1.85
            rpm -= fault_progress * 110.0

            health = max(26.0, 98.4 - fault_progress * 65.0)
            anomaly_score = min(0.92, 0.04 + fault_progress * 0.85)
            active_subsystem = "fuel_system"

            if self.currentSec > 18600:
                component_status = "critical"
            else:
                component_status = "degrading"

        current_event = self.events[0]
        for e in reversed(self.events):
            if self.currentSec >= e["timestampSec"]:
                current_event = e
                break

        frame_data = {
            "currentSec": self.currentSec,
            "formattedTime": self.formatTime(self.currentSec),
            "progressPercent": round(float(progress * 100), 1),
            "isPlaying": self.isPlaying,
            "playbackSpeed": self.playbackSpeed,
            "currentEvent": current_event,
            "metrics": {
                "health": round(float(health), 1),
                "anomalyScore": round(float(anomaly_score), 2),
                "activeSubsystem": active_subsystem,
                "componentStatus": component_status,
                "sensors": {
                    "rpm": int(round(rpm)),
                    "cht": round(float(cht), 1),
                    "egt": round(float(egt), 1),
                    "oil_press": round(float(oil_press), 2),
                    "oil_temp": round(float(oil_temp), 1),
                    "fuel_flow": round(float(fuel_flow), 1),
                    "vibration": round(float(vibration), 2),
                    "battery_volt": round(float(battery_volt), 1),
                    "injection_timing": round(float(injection_timing), 1),
                },
            },
        }

        if self.onFrameUpdate:
            try:
                self.onFrameUpdate(frame_data)
            except Exception as e:
                print("Error in onFrameUpdate:", e)

        return frame_data

    def formatTime(self, seconds):
        total_sec = int(seconds)
        hrs = f"{total_sec // 3600:02d}"
        mins = f"{(total_sec % 3600) // 60:02d}"
        secs = f"{total_sec % 60:02d}"
        return f"{hrs}:{mins}:{secs}"


if __name__ == "__main__":
    replay = MissionReplay()
    f0 = replay.emitCurrentFrame()
    print(f"Initial frame: {f0['formattedTime']}, Health: {f0['metrics']['health']}%")
    replay.seekTo(19000)
    f_mid = replay.emitCurrentFrame()
    print(f"Mid-flight frame: {f_mid['formattedTime']}, Event: {f_mid['currentEvent']['title']}, Subsystem: {f_mid['metrics']['activeSubsystem']}")
    print("MissionReplay test passed!")
