#!/usr/bin/env python3
import os
import asyncio
import json
import threading
import time
import logging
from typing import Dict, Any, Optional, List

import can
from can.exceptions import CanInterfaceNotImplementedError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from rvc_decoder import load_config_data, decode_payload

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,  # switch to DEBUG to see raw frames
    format="%(asctime)s %(levelname)7s %(message)s",
)

# ── Metrics ─────────────────────────────────────────────────────────────────
FRAME_COUNTER = Counter("rvc2api_frames_total", "Total CAN frames received")
DECODE_ERRORS = Counter("rvc2api_decode_errors_total", "Total decode errors")
LOOKUP_MISSES = Counter("rvc2api_lookup_misses_total", "Total device‑lookup misses")
WS_CLIENTS    = Gauge("rvc2api_ws_clients", "Active WebSocket clients")
FRAME_LATENCY = Histogram("rvc2api_frame_latency_seconds", "Time spent decoding & dispatching frames")

# ── Load spec & mappings ─────────────────────────────────────────────────────
spec_override    = os.getenv("CAN_SPEC_PATH")
mapping_override = os.getenv("CAN_MAP_PATH")
(
    decoder_map,
    raw_device_mapping,
    device_lookup,
    status_lookup,
    light_entity_ids,
    entity_id_lookup,
    light_command_info,
) = load_config_data(
    rvc_spec_path_override=spec_override,
    device_mapping_path_override=mapping_override,
)

# ── FastAPI ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="rvc2api",
    servers=[{"url": "http://localhost:8000", "description": "Holtel"}],
)

# In‑memory state: entity_id → payload
state: Dict[str, Dict[str, Any]] = {}

# ── Pre‑seed lights (off state) ───────────────────────────────────────────────
now = time.time()
for eid in light_entity_ids:
    info = light_command_info.get(eid)
    if not info:
        continue
    # find the spec entry for this DGN
    spec_entry = next(
        entry for entry in decoder_map.values()
        if entry["dgn_hex"].upper() == format(info["dgn"], "X")
    )
    # default 8‑byte off payload (all zeros)
    decoded, raw = decode_payload(spec_entry, bytes([0]*8))
    state[eid] = {
        "entity_id": eid,
        "value": decoded,
        "raw": raw,
        "timestamp": now,
    }

# Active WebSocket clients
clients: set[WebSocket] = set()

# ── Models ──────────────────────────────────────────────────────────────────
class Entity(BaseModel):
    entity_id: str
    value: Dict[str, str]
    raw: Dict[str, int]
    timestamp: float


# ── Broadcasting ────────────────────────────────────────────────────────────
async def broadcast_to_clients(text: str):
    for ws in list(clients):
        try:
            await ws.send_text(text)
        except Exception:
            clients.discard(ws)
    WS_CLIENTS.set(len(clients))

# ── CAN Reader Startup ──────────────────────────────────────────────────────
@app.on_event("startup")
async def start_can_readers():
    loop = asyncio.get_running_loop()
    raw_ifaces = os.getenv("CAN_CHANNELS", "can0,can1")
    interfaces = [i.strip() for i in raw_ifaces.split(",") if i.strip()]
    bustype = os.getenv("CAN_BUSTYPE", "socketcan")
    bitrate = int(os.getenv("CAN_BITRATE", "500000"))

    for iface in interfaces:
        def reader(iface=iface):
            try:
                bus = can.interface.Bus(channel=iface, bustype=bustype, bitrate=bitrate)
            except CanInterfaceNotImplementedError as e:
                logging.error(f"Cannot open CAN bus '{iface}' ({bustype}): {e}")
                return

            logging.info(f"Started CAN reader on {iface} via {bustype} @ {bitrate}bps")
            while True:
                msg = bus.recv(timeout=1.0)
                if msg is None:
                    continue

                FRAME_COUNTER.inc()
                start = time.perf_counter()
                try:
                    entry = decoder_map.get(msg.arbitration_id)
                    if not entry:
                        LOOKUP_MISSES.inc()
                        continue
                    decoded, raw = decode_payload(entry, msg.data)
                except Exception:
                    DECODE_ERRORS.inc()
                    continue
                finally:
                    FRAME_LATENCY.observe(time.perf_counter() - start)

                dgn = entry.get("dgn_hex")
                inst = raw.get("instance")
                if not dgn or inst is None:
                    LOOKUP_MISSES.inc()
                    continue

                key = (dgn.upper(), str(inst))
                device = (
                    status_lookup.get(key)
                    or status_lookup.get((dgn.upper(), "default"))
                    or device_lookup.get(key)
                    or device_lookup.get((dgn.upper(), "default"))
                )
                if not device:
                    LOOKUP_MISSES.inc()
                    logging.info(f"No device config for {key}, PGN 0x{msg.arbitration_id:X}")
                    continue

                eid = device["entity_id"]
                ts = time.time()
                payload = {"entity_id": eid, "value": decoded, "raw": raw, "timestamp": ts}
                state[eid] = payload
                text = json.dumps(payload)
                loop.call_soon_threadsafe(lambda t=text: loop.create_task(broadcast_to_clients(t)))

        threading.Thread(target=reader, daemon=True).start()


# ── REST Endpoints ─────────────────────────────────────────────────────────
@app.get("/entities", response_model=Dict[str, Entity])
async def list_entities(
    type: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
):
    """
    Return all entities, optionally filtered by device_type and/or area.
    """
    def matches(eid: str) -> bool:
        cfg = entity_id_lookup.get(eid, {})
        if type and cfg.get("device_type") != type:
            return False
        if area and cfg.get("suggested_area") != area:
            return False
        return True

    return {eid: ent for eid, ent in state.items() if matches(eid)}


@app.get("/entities/ids", response_model=List[str])
async def list_entity_ids():
    """Return all known entity IDs."""
    return list(state.keys())


@app.get("/entities/{entity_id}", response_model=Entity)
async def get_entity(entity_id: str):
    """Return the latest value for one entity."""
    ent = state.get(entity_id)
    if not ent:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ent


@app.get("/lights", response_model=Dict[str, Entity])
async def list_lights(
    state_filter: Optional[str] = Query(None, alias="state", description="Filter by 'on'/'off'"),
    capability:    Optional[str] = Query(None, description="e.g. 'brightness' or 'on_off'"),
    area:          Optional[str] = Query(None),
):
    """
    Return lights, optionally filtered by:
    - state ('on' or 'off')
    - a specific capability (e.g. 'brightness')
    - area (suggested_area)
    """
    results: Dict[str, Entity] = {}
    for eid, ent in state.items():
        if eid not in light_entity_ids:
            continue

        cfg = entity_id_lookup.get(eid, {})
        if area and cfg.get("suggested_area") != area:
            continue

        caps = cfg.get("capabilities", [])
        if capability and capability not in caps:
            continue

        if state_filter:
            val = ent["value"].get("OnOff") or ent["value"].get("on_off") or ent["value"].get("state")
            if not val or val.lower() != state_filter.lower():
                continue

        results[eid] = ent

    return results


@app.get("/meta", response_model=Dict[str, List[str]])
async def metadata():
    """
    Expose groupable dimensions:
    - type      (device_type)
    - area      (suggested_area)
    - capability
    """
    mapping = {
        "type":       "device_type",
        "area":       "suggested_area",
        "capability": "capabilities",
    }
    out: Dict[str, List[str]] = {}
    for public, internal in mapping.items():
        vals = {
            cfg.get(internal)
            for cfg in entity_id_lookup.values()
            if cfg.get(internal)
        }
        # Flatten for lists of lists:
        flat = []
        for v in vals:
            if isinstance(v, list):
                flat.extend(v)
            else:
                flat.append(v)
        out[public] = sorted(set(flat))  # type: ignore[list]
    return out


@app.get("/healthz")
async def healthz():
    """Liveness probe."""
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.get("/readyz")
async def readyz():
    """
    Readiness probe: 200 once at least one frame decoded, else 503.
    """
    ready = len(state) > 0
    code = 200 if ready else 503
    return JSONResponse(status_code=code, content={"status": "ready" if ready else "pending", "entities": len(state)})


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket endpoint: push every new payload as JSON.
    """
    await ws.accept()
    clients.add(ws)
    WS_CLIENTS.set(len(clients))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.discard(ws)
        WS_CLIENTS.set(len(clients))
