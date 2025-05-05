import asyncio
import json
import threading
import time
from typing import Dict, Any

import can
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from rvc_decoder import load_config_data, decode_payload

# Load spec & mapping from package data
(
    decoder_map,
    device_mapping,
    device_lookup,
    status_lookup,
    light_entity_ids,
    entity_id_lookup,
    light_command_info,
) = load_config_data()

app = FastAPI(title="rvc2api")

# In‑memory state: entity_id → last payload
state: Dict[str, Dict[str, Any]] = {}
# Active WebSocket connections
clients: set[WebSocket] = set()

class Entity(BaseModel):
    entity_id: str
    value: Dict[str, str]
    raw: Dict[str, int]
    timestamp: float

@app.on_event("startup")
def start_can_readers():
    """
    On app startup, spawn a thread per CAN interface reading frames,
    decoding them, updating `state`, and broadcasting to WebSocket clients.
    """
    interfaces = ["can0", "can1"]  # adjust as needed

    def reader(iface: str):
        bus = can.interface.Bus(channel=iface, interface="socketcan")
        while True:
            msg = bus.recv(timeout=1.0)
            if not msg:
                continue

            entry = decoder_map.get(msg.arbitration_id)
            if not entry:
                continue

            decoded, raw = decode_payload(entry, msg.data)
            key = (entry["dgn_hex"], str(entry.get("instance", 0)))
            device = status_lookup.get(key) or device_lookup.get(key)
            if not device:
                continue

            eid = device["entity_id"]
            ts = time.time()
            payload = {"entity_id": eid, "value": decoded, "raw": raw, "timestamp": ts}
            state[eid] = payload

            text = json.dumps(payload)
            for ws in list(clients):
                # Use asyncio to send from a thread
                asyncio.run(ws.send_text(text))

    for iface in interfaces:
        t = threading.Thread(target=reader, args=(iface,), daemon=True)
        t.start()

@app.get("/entities", response_model=Dict[str, Entity])
async def list_entities():
    """
    Return a snapshot of all known entities and their last values.
    """
    return state

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket that pushes every new payload as JSON.
    """
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            # keep connection open; ignore incoming messages
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.remove(ws)
