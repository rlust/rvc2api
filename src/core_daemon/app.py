#!/usr/bin/env python3
import os
import asyncio
import json
import threading
import time
import logging
from typing import Dict, Any, Optional, List
from collections import deque

import can
from can.exceptions import CanInterfaceNotImplementedError
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Query, Response
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from rvc_decoder import load_config_data, decode_payload

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)7s %(message)s",
)

# ── Metrics ─────────────────────────────────────────────────────────────────
FRAME_COUNTER       = Counter("rvc2api_frames_total", "Total CAN frames received")
DECODE_ERRORS       = Counter("rvc2api_decode_errors_total", "Total decode errors")
LOOKUP_MISSES       = Counter("rvc2api_lookup_misses_total", "Total device‑lookup misses")
SUCCESSFUL_DECODES  = Counter("rvc2api_successful_decodes_total", "Total successful decodes")
WS_CLIENTS          = Gauge("rvc2api_ws_clients", "Active WebSocket clients")
WS_MESSAGES         = Counter("rvc2api_ws_messages_total", "Total WebSocket messages sent")
ENTITY_COUNT        = Gauge("rvc2api_entity_count", "Number of entities in current state")
HISTORY_SIZE_GAUGE  = Gauge("rvc2api_history_size", "Number of stored historical samples per entity", ["entity_id"])
FRAME_LATENCY       = Histogram("rvc2api_frame_latency_seconds", "Time spent decoding & dispatching frames")
HTTP_REQUESTS       = Counter("rvc2api_http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code"])
HTTP_LATENCY        = Histogram("rvc2api_http_request_latency_seconds", "HTTP request latency in seconds", ["method", "endpoint"])

# Suggested by RV-C spec:
PGN_USAGE_COUNTER    = Counter("rvc2api_pgn_usage_total", "PGN usage by frame count", ["pgn"])
INST_USAGE_COUNTER   = Counter("rvc2api_instance_usage_total", "Instance usage by DGN", ["dgn", "instance"])
DGN_TYPE_GAUGE       = Gauge("rvc2api_dgn_type_present", "Number of DGNs seen per type/class", ["device_type"])

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

# ── FastAPI setup ──────────────────────────────────────────────────────────
app = FastAPI(
    title="Holtel rvc2api",
    servers=[{"url": "/", "description": "Holtel de Assfire"}],
)

# ── HTTP middleware for Prometheus ─────────────────────────────────────────
@app.middleware("http")
async def prometheus_http_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    latency = time.perf_counter() - start

    path = request.url.path
    method = request.method
    status = response.status_code

    HTTP_REQUESTS.labels(method=method, endpoint=path, status_code=status).inc()
    HTTP_LATENCY.labels(method=method, endpoint=path).observe(latency)
    return response

# ── In‑memory state + history ────────────────────────────────────────────────
state: Dict[str, Dict[str, Any]] = {}
HISTORY_DURATION = 24 * 3600  # seconds
history: Dict[str, deque[Dict[str, Any]]] = {
    eid: deque() for eid in entity_id_lookup
}

# ── Pre‑seed lights (off state) ───────────────────────────────────────────────
now = time.time()
for eid in light_entity_ids:
    info = light_command_info.get(eid)
    if not info:
        continue
    spec_entry = next(
        entry for entry in decoder_map.values()
        if entry["dgn_hex"].upper() == format(info["dgn"], "X")
    )
    decoded, raw = decode_payload(spec_entry, bytes([0] * 8))
    payload = {"entity_id": eid, "value": decoded, "raw": raw, "timestamp": now}
    state[eid] = payload
    history[eid].append(payload)
ENTITY_COUNT.set(len(state))
for eid in history:
    HISTORY_SIZE_GAUGE.labels(entity_id=eid).set(len(history[eid]))

# ── Active WebSocket clients ────────────────────────────────────────────────
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
            WS_MESSAGES.inc()
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
                    SUCCESSFUL_DECODES.inc()
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

                # --- Custom Metrics ---
                pgn = msg.arbitration_id & 0x3FFFF
                PGN_USAGE_COUNTER.labels(pgn=f"{pgn:X}").inc()
                INST_USAGE_COUNTER.labels(dgn=dgn.upper(), instance=str(inst)).inc()
                device_type = device.get("device_type", "unknown")
                DGN_TYPE_GAUGE.labels(device_type=device_type).set(1)

                # update state
                state[eid] = payload
                ENTITY_COUNT.set(len(state))

                # record into time‑based history
                hq = history[eid]
                hq.append(payload)
                cutoff = ts - HISTORY_DURATION
                while hq and hq[0]["timestamp"] < cutoff:
                    hq.popleft()
                HISTORY_SIZE_GAUGE.labels(entity_id=eid).set(len(hq))

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

@app.get("/entities/{entity_id}/history", response_model=List[Entity])
async def get_history(
    entity_id: str,
    since: Optional[float] = Query(None, description="Unix timestamp; only entries newer than this"),
    limit: Optional[int] = Query(1000, ge=1, description="Max number of points to return"),
):
    if entity_id not in history:
        raise HTTPException(status_code=404, detail="Entity not found")
    entries = list(history[entity_id])
    if since is not None:
        entries = [e for e in entries if e["timestamp"] > since]
    return entries[-limit:]

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
        values = set()
        for cfg in entity_id_lookup.values():
            val = cfg.get(internal)
            if isinstance(val, list):
                values.update(val)
            elif val is not None:
                values.add(val)
        out[public] = sorted(values)

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

@app.exception_handler(ResponseValidationError)
async def validation_exception_handler(request, exc):
    return PlainTextResponse(f"Validation error: {exc}", status_code=500)
