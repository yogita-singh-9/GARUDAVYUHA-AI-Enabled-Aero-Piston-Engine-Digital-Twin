"""
layer1_physics.py
=================
LAYER 1: Physics & Environmental Simulation Twin (male_uav_digital_twin)

Simulates the Rotax 914 / VRDE Tapas aero-piston engine on a continuous
500 ms loop (per the SIH26054 execution blueprint), using the shared
`engine_model` core so every number this emits is reproducible and matches
the equations proved out in Feasibility1.pdf.

Responsibilities:
  1. Runs the physics loop and streams telemetry via UDP to Layer 2
     (127.0.0.1:9999 by default - see config.json -> network).
  2. Listens on a second UDP socket (127.0.0.1:9998) for JSON commands from
     the dashboard's Mission Simulator tab ("Send scenario to Layer 1") and
     from a simple keyboard fault injector, letting an operator change
     ambient_temp / altitude_ft / inject a fault live.
  3. Every outgoing packet is HMAC-signed (SHA-256) with the shared secret
     in config.json so Layer 2 can validate link integrity, simulating a
     military-grade telemetry link per the tech-stack doc.

Run standalone:  python layer1_physics.py
"""
from __future__ import annotations
import hashlib
import hmac
import json
import socket
import threading
import time

import numpy as np

from engine_model import load_config, active_engine_params, step_state

CFG = load_config()
META = active_engine_params(CFG)
NET = CFG["network"]
SECRET = bytes.fromhex(CFG["security"]["secret_key_hex"])

COMMAND_PORT = NET["layer1_command_udp_port"]
TELEMETRY_PORT = NET["layer2_telemetry_udp_port"]
TELEMETRY_HOST = NET["layer2_host"]
LOOP_SECONDS = CFG["sampling"]["physics_loop_seconds"]

rng = np.random.default_rng(7)

# Mutable shared state, protected by a lock since the command listener runs
# on a background thread while the main loop reads/writes it every tick.
_state_lock = threading.Lock()
STATE = {
    "flight_hours": 480.0,   # start mid-life so RUL / degradation is visible in the demo
    "ambient_temp": 15.0,
    "altitude_ft": 5000.0,
    "fault_injected": {},
}


def sign(payload_bytes: bytes) -> str:
    return hmac.new(SECRET, payload_bytes, hashlib.sha256).hexdigest()


def send_telemetry(sock: socket.socket, packet: dict) -> None:
    body = json.dumps(packet, default=float).encode()
    envelope = {"sig": sign(body), "data": packet}
    sock.sendto(json.dumps(envelope).encode(), (TELEMETRY_HOST, TELEMETRY_PORT))


def command_listener() -> None:
    """LAYER 1 keyboard/dashboard fault + scenario injector.
    Accepts JSON like: {"ambient_temp": 45, "altitude_ft": 10200, "duration_hrs": 4}
    or {"fault": "vibration_spike"} / {"fault": "overheat"} / {"fault": "clear"}.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", COMMAND_PORT))
    print(f"[LAYER 1] Command listener bound on 127.0.0.1:{COMMAND_PORT}")
    while True:
        try:
            data, _ = sock.recvfrom(4096)
            command = json.loads(data.decode())
            with _state_lock:
                if "ambient_temp" in command:
                    STATE["ambient_temp"] = float(command["ambient_temp"])
                if "altitude_ft" in command:
                    STATE["altitude_ft"] = float(command["altitude_ft"])
                if "duration_hrs" in command:
                    # duration is informational for the dashboard; Layer 1 just
                    # keeps running continuously, so we log it only.
                    pass
                fault = command.get("fault")
                if fault == "overheat":
                    STATE["fault_injected"] = {"cht_bump": 22.0, "vibration_bump": 0.05}
                elif fault == "vibration_spike":
                    STATE["fault_injected"] = {"cht_bump": 2.0, "vibration_bump": 1.4}
                elif fault == "clear":
                    STATE["fault_injected"] = {}
            print(f"[LAYER 1] Environment/command updated: {command}")
        except Exception as e:  # noqa: BLE001 - simulator must never crash the loop
            print(f"[LAYER 1] Command listener error: {e}")


def main() -> None:
    threading.Thread(target=command_listener, daemon=True).start()
    tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print("[LAYER 1] Physics & Environmental Simulation Twin starting...")
    print(f"[LAYER 1] Active engine: {META['display_name']}")
    print(f"[LAYER 1] Streaming telemetry -> udp://{TELEMETRY_HOST}:{TELEMETRY_PORT} "
          f"every {LOOP_SECONDS}s")

    dt_hours = LOOP_SECONDS / 3600.0
    while True:
        loop_start = time.time()
        with _state_lock:
            state_snapshot = dict(STATE)
        packet, new_state = step_state(state_snapshot, META, dt_hours, rng=rng)
        with _state_lock:
            STATE["flight_hours"] = new_state["flight_hours"]
        packet["timestamp"] = time.time()
        packet["engine"] = CFG["active_engine"]
        try:
            send_telemetry(tx_sock, packet)
        except Exception as e:  # noqa: BLE001
            print(f"[LAYER 1] Telemetry send error: {e}")
        elapsed = time.time() - loop_start
        time.sleep(max(0.0, LOOP_SECONDS - elapsed))


if __name__ == "__main__":
    main()
