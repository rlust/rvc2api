#!/usr/bin/env python3
import os
import asyncio
import json
import threading
import time
import logging
from typing import Dict, Any

import can
from can.exceptions import CanInterfaceNotImplementedError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from rvc_decoder import load_config_data, decode_payload

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)7s %(message)s",
)

# Load your spec and mapping, allowing overrides
spec_path    = os.getenv("CAN_SPEC_PATH")    # e.g. "/etc/rvc2api/rvc.json"
mapping_path = os.getenv("CAN_MAP_PATH")     # e.g. "/etc/rvc2api/device_mapping.yml"
decoder_map, device_mapping, device_lookup, status_lookup, \
    light_entity_ids, entity_id_lookup, light_command_info = load_config_data(
        rvc_spec_path=spec_path,
        device_mapping_path=mapping_path
    )

app = FastAPI(title="rvc2api")

# In‑memory state: entity_id → last payload
state: Dict[str, Dict[str, Any]] = {}
# Connected WebSocket clients
clients: set[WebSocket] = set()

class Entity(BaseModel):
    entity_id: str
    value: Dict[str, str]
    raw: Dict[str, int]
    timestamp: float

async def broadcast_to_clients(text: str):
    for ws in list(clients):
        try:
            await ws.send_text(text)
        except Exception:
            clients.discard(ws)

@app.on_event("startup")
async def start_can_readers():
    loop = asyncio.get_running_loop()

    # Read interface config from env, default to can0,can1
    raw_ifaces = os.getenv("CAN_CHANNELS", "can0,can1")
    interfaces = [iface.strip() for iface in raw_ifaces.split(",") if iface.strip()]

    bustype = os.getenv("CAN_BUSTYPE", "socketcan")
    bitrate = int(os.getenv("CAN_BITRATE", "500000"))

    for iface in interfaces:
        def reader(iface=iface):
            try:
                bus = can.interface.Bus(
                    channel=iface,
                    bustype=bustype,
                    bitrate=bitrate,
                )
            except CanInterfaceNotImplementedError as e:
                logging.error(f"Cannot open CAN bus '{iface}' (bustype={bustype}): {e}")
                return

            logging.info(f"Started CAN reader on {iface} via {bustype} @ {bitrate}bps")

            while True:
                msg = bus.recv(timeout=1.0)
                if msg is None:
                    continue

                logging.debug(f"RAW frame: id=0x{msg.arbitration_id:X} data={list(msg.data)}")

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
                payload = {
                    "entity_id": eid,
                    "value": decoded,
                    "raw": raw,
                    "timestamp": ts,
                }
                state[eid] = payload

                text = json.dumps(payload)
                # schedule broadcast on the main loop
                loop.call_soon_threadsafe(lambda t=text: loop.create_task(broadcast_to_clients(t)))

        t = threading.Thread(target=reader, daemon=True)
        t.start()

@app.get("/entities", response_model=Dict[str, Entity])
async def list_entities():
    return state

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.discard(ws)
