"""
layer2_pipeline.py
===================
LAYER 2: Data Ingestion & Edge Pipeline Hub (male_uav_digital_twin)
LAYER 5: Historical Analytics & Flight Replay (black-box CSV logger, embedded here)
LAYER 6: Federated Fleet Management export endpoint

Acts as the local Ground Control Station (GCS) Data Bus:
  - Ingests Layer 1 telemetry over UDP (127.0.0.1:9999), verifying the
    HMAC-SHA256 signature on every packet for link-integrity (simulating a
    military-grade telemetry link).
  - Passes each packet through Layer 3's AdvancedDiagnosticEngine.
  - Appends the enriched packet to mission_log.csv (append-only black box).
  - Broadcasts the enriched packet to every connected WebSocket client at
    ws://127.0.0.1:8000/ws/telemetry (this is what Layer 4's dashboard
    subscribes to).
  - Exposes REST fallbacks (/api/latest, /api/history) so the dashboard can
    also work via simple polling if a WebSocket client isn't available, and
    /api/fleet/export for Layer 6.

Run standalone:  uvicorn layer2_pipeline:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import asyncio
import csv
import hashlib
import hmac
import json
import os
import socket
import time
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from engine_model import load_config
from layer3_intelligence import AdvancedDiagnosticEngine

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = load_config()
NET = CFG["network"]
SECRET = bytes.fromhex(CFG["security"]["secret_key_hex"])

CSV_FILE = os.path.join(HERE, "mission_log.csv")
FIELDNAMES = [
    "timestamp", "flight_hours", "ambient_temp", "altitude_ft", "rpm", "cht",
    "egt", "fuel_flow", "oil_pressure", "vibration", "dynamic_thermal_limit",
    "mission_abort", "anomaly_score", "anomaly_flag", "severity",
    "most_likely_fault", "confidence_pct", "rul_hours", "rul_ci_hours",
]

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_csv_header()
    await start_udp_intake()
    print("[LAYER 2] GCS Data Bus ready.")
    yield

app = FastAPI(title="GARUDAVYUHA Layer 2 - GCS Data Bus", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self):
        self.active_sockets: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_sockets.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active_sockets.discard(ws)

    async def broadcast(self, data: dict):
        msg = json.dumps(data, default=float)
        dead = []
        for ws in list(self.active_sockets):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
ml_engine = AdvancedDiagnosticEngine()

# In-memory state shared between the UDP intake loop and the REST endpoints.
LATEST_PACKET: dict = {}
HISTORY: deque = deque(maxlen=500)
EVENTS: deque = deque(maxlen=100)
_csv_lock = asyncio.Lock()


def _ensure_csv_header():
    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        with open(CSV_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def verify_signature(envelope: dict) -> bool:
    try:
        body = json.dumps(envelope["data"], default=float).encode()
        expected = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, envelope["sig"])
    except Exception:
        return False


async def append_csv_row(row: dict):
    async with _csv_lock:
        with open(CSV_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            writer.writerow(row)


def _maybe_log_event(enriched: dict):
    if enriched.get("anomaly_flag"):
        EVENTS.appendleft({
            "timestamp": enriched["timestamp"],
            "message": f"AI flagged {enriched['most_likely_fault']} "
                       f"(severity {enriched['severity']}, score {enriched['anomaly_score']})",
        })
    if enriched.get("mission_abort"):
        EVENTS.appendleft({
            "timestamp": enriched["timestamp"],
            "message": "THRESHOLD BREACH - CHT exceeded dynamic thermal limit",
        })


class UDPIntakeProtocol(asyncio.DatagramProtocol):
    """Layer 1 -> Layer 2 ingestion transport (UDP datagram, HMAC-verified)."""

    def datagram_received(self, data: bytes, addr):
        asyncio.create_task(self._handle(data))

    async def _handle(self, data: bytes):
        try:
            envelope = json.loads(data.decode())
        except Exception:
            return
        if not verify_signature(envelope):
            EVENTS.appendleft({"timestamp": time.time(),
                               "message": "REJECTED packet - invalid HMAC signature"})
            return
        packet = envelope["data"]
        diagnostics = ml_engine.evaluate_packet(packet)
        enriched = {**packet, **diagnostics, "timestamp": packet.get("timestamp", time.time())}

        LATEST_PACKET.clear()
        LATEST_PACKET.update(enriched)
        HISTORY.append(enriched)
        _maybe_log_event(enriched)

        await append_csv_row(enriched)
        await manager.broadcast(enriched)


async def start_udp_intake():
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(
        UDPIntakeProtocol, local_addr=("127.0.0.1", NET["layer2_telemetry_udp_port"])
    )
    print(f"[LAYER 2] UDP telemetry intake listening on "
          f"127.0.0.1:{NET['layer2_telemetry_udp_port']}")


# Lifespan handles startup now


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    """Layer 4 dashboard subscribes here for real-time push updates."""
    await manager.connect(ws)
    try:
        if LATEST_PACKET:
            await ws.send_text(json.dumps(LATEST_PACKET, default=float))
        while True:
            # Keep the connection alive; we don't expect inbound messages, but
            # reading with a timeout lets us detect client disconnects promptly.
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


@app.get("/api/latest")
async def api_latest():
    return LATEST_PACKET or {"status": "waiting_for_telemetry"}


@app.get("/api/history")
async def api_history(limit: int = 200):
    return list(HISTORY)[-limit:]


@app.get("/api/events")
async def api_events(limit: int = 50):
    return list(EVENTS)[:limit]


@app.get("/api/fleet/export")
async def api_fleet_export(node_id: str = "fleet_node_01"):
    payload = ml_engine.export_fleet_node(node_id)
    out_path = os.path.join(HERE, f"{node_id}.json")
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    return payload


@app.get("/api/health")
async def api_health():
    return {"status": "ok", "connected_clients": len(manager.active_sockets),
            "rows_logged": len(HISTORY)}


from fastapi import Request

@app.post("/api/v1/diagnose")
async def api_diagnose(request: Request):
    payload = await request.json()
    start_t = time.time()
    
    packet = payload.get("sensors", {})
    packet["timestamp"] = payload.get("timestamp", time.time())
    
    try:
        diagnostics = ml_engine.evaluate_packet(packet)
    except Exception as e:
        return {"error": str(e)}
        
    latency_ms = (time.time() - start_t) * 1000
    
    shap_attr = []
    for item in diagnostics.get("xai_contributions", []):
        z = item["z_score"]
        weight = min(100.0, abs(z) * 10.0) 
        shap_attr.append({
            "parameter": item["feature"],
            "weight": round(weight, 1),
            "direction": "up" if z > 0 else "down"
        })
        
    return {
        "anomalyScore": diagnostics.get("anomaly_score", 0),
        "mostLikelyFault": diagnostics.get("most_likely_fault", "Nominal Operation"),
        "shapAttribution": shap_attr,
        "predictedRUL": diagnostics.get("rul_hours", 0),
        "inferenceLatencyMs": round(latency_ms, 2)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("layer2_pipeline:app", host="0.0.0.0", port=NET["layer2_ws_port"], reload=False)
