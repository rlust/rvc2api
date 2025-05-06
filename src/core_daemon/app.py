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
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Query, Response, Body
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from rvc_decoder import load_config_data, decode_payload

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
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

# Queue for CAN messages to be sent
CAN_TX_QUEUE_LENGTH = Gauge("rvc2api_can_tx_queue_length", "Number of pending messages in the CAN transmit queue")
CAN_TX_ENQUEUE_TOTAL = Counter("rvc2api_can_tx_enqueue_total", "Total number of messages enqueued to the CAN transmit queue")
CAN_TX_ENQUEUE_LATENCY = Histogram("rvc2api_can_tx_enqueue_latency_seconds", "Latency for enqueueing CAN control messages")

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

# ── Active CAN buses ─────────────────────────────────────────────────────────
buses: Dict[str, can.Bus] = {}

# ── CAN Transmit Queue ───────────────────────────────────────────────────────
can_tx_queue: asyncio.Queue[tuple[can.Message, str]] = asyncio.Queue()

async def can_writer():
    bustype = os.getenv("CAN_BUSTYPE", "socketcan")
    while True:
        msg, interface = await can_tx_queue.get()
        CAN_TX_QUEUE_LENGTH.set(can_tx_queue.qsize())

        try:
            bus = buses.get(interface)
            if not bus:
                try:
                    bus = can.interface.Bus(channel=interface, bustype=bustype)
                    buses[interface] = bus
                except Exception as e:
                    logging.error(f"Failed to initialize CAN bus '{interface}': {e}")
                    can_tx_queue.task_done()
                    continue

            try:
                bus.send(msg)
                await asyncio.sleep(0.05)
                bus.send(msg)
            except Exception as e:
                logging.error(f"CAN writer failed on {interface}: {e}")
        except Exception as e:
            logging.error(f"CAN writer failed on {interface}: {e}")
        finally:
            can_tx_queue.task_done()
            CAN_TX_QUEUE_LENGTH.set(can_tx_queue.qsize())

@app.on_event("startup")
async def start_can_writer():
    asyncio.create_task(can_writer())

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

    # Add human-readable state
    brightness = raw.get("operating status (brightness)", 0)
    human_state = "on" if brightness > 0 else "off"

    payload = {
        "entity_id": eid,
        "value": decoded,
        "raw": raw,
        "state": human_state,
        "timestamp": now
    }
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
    state: str
    timestamp: float

class ControlCommand(BaseModel):
    command: str  # One of: "set", "toggle", "brightness_up", "brightness_down"
    state: Optional[str] = Field(
        default=None,
        description="Target state: 'on' or 'off'. Required only for 'set' command."
    )

    brightness: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Brightness percent (0–100). Only used when command is 'set' and state is 'on'."
    )

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
                buses[iface] = bus
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
                # Determine human-readable state
                # Use the likely correct signal name "Operating Status (Brightness)"
                raw_brightness = raw.get("Operating Status (Brightness)", 0)
                state_str = "on" if raw_brightness > 0 else "off"

                payload = {
                    "entity_id": eid,
                    "value": decoded,
                    "raw": raw,
                    "state": state_str,  # 👈 new field
                    "timestamp": ts
                }

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
    state_filter:  Optional[str] = Query(None, alias="state", description="Filter by 'on'/'off'"),
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
            val = ent.get("state")
            if not val or val.strip().lower() != state_filter.strip().lower():
                continue
        results[eid] = ent
    return results

@app.get("/meta", response_model=Dict[str, List[str]])
async def metadata():
    """
    Expose groupable dimensions:
    - type        (device_type)
    - area        (suggested_area)
    - capability  (defined in mapping)
    - command     (derived from capabilities)
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

    # Include derived command set based on capabilities
    command_set = set()
    for eid, cfg in entity_id_lookup.items():
        if eid in light_command_info:
            caps = cfg.get("capabilities", [])
            command_set.add("on_off")
            command_set.add("set")
            command_set.add("toggle")
            if "brightness" in caps:
                command_set.add("brightness")
                command_set.add("brightness_increase")
                command_set.add("brightness_decrease")
    out["command"] = sorted(command_set)

    # Ensure all keys are included
    for key in ["type", "area", "capability", "command"]:
        out.setdefault(key, [])

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

@app.post("/entities/{entity_id}/control")
async def control_entity(
    entity_id: str,
    cmd: ControlCommand = Body(..., examples={
        "turn_on": {
            "summary": "Turn light on",
            "value": {"command": "set", "state": "on"}
        },
        "turn_off": {
            "summary": "Turn light off",
            "value": {"command": "set", "state": "off"}
        },
        "set_brightness": {
            "summary": "Set brightness to 75%",
            "value": {"command": "set", "state": "on", "brightness": 75}
        },
        "toggle": {
            "summary": "Toggle current state",
            "value": {"command": "toggle"}
        },
        "brightness_up": {
            "summary": "Increase brightness by 10%",
            "value": {"command": "brightness_up"}
        },
        "brightness_down": {
            "summary": "Decrease brightness by 10%",
            "value": {"command": "brightness_down"}
        }
    })
):
    device = entity_id_lookup.get(entity_id)
    if not device:
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity_id not in light_command_info:
        raise HTTPException(status_code=400, detail="Entity is not controllable")

    info = light_command_info[entity_id]
    pgn = info["dgn"] # This is the PGN, e.g., 0x1FEDB for DC_DIMMER_COMMAND_2
    instance = info["instance"]
    interface = info["interface"]

    # --- Read Current State ---
    current_state_data = state.get(entity_id, {})

    # Determine current_on using the reader's pre-calculated "state" field
    current_on_str = current_state_data.get("state", "off") # Default to "off" if not found
    current_on = current_on_str.lower() == "on"

    # Determine current_brightness_ui using the likely correct signal name
    current_raw_values = current_state_data.get("raw", {})
    # The reader thread in app.py uses "Operating Status (Brightness)" to determine its "state" field.
    # We rely on that key for the current raw brightness value.
    current_brightness_raw = current_raw_values.get("Operating Status (Brightness)", 0) # Default to 0 if key not found
    
    current_brightness_ui = 0
    # Ensure raw value is treated as a number, scale it to UI percentage (0-100)
    # Assuming raw 0-200 maps to UI 0-100%
    if isinstance(current_brightness_raw, (int, float)):
        current_brightness_ui = min(int(current_brightness_raw) // 2, 100)
    
    # --- Determine Target State ---
    target_brightness_ui = current_brightness_ui # Default: no change in brightness if already on
    action = "No change"

    if cmd.command == "set":
        if cmd.state not in {"on", "off"}:
            raise HTTPException(status_code=400, detail="State must be 'on' or 'off' for set command")
        if cmd.state == "on":
            # If brightness is specified, use it. 
            # Else, if light is already on, keep its current brightness.
            # Else (light is off and turning on without specific brightness), set to 100%.
            if cmd.brightness is not None:
                target_brightness_ui = cmd.brightness
            elif not current_on: # Turning on from off state, and no brightness specified
                target_brightness_ui = 100
            # If current_on is true and cmd.brightness is None, target_brightness_ui remains current_brightness_ui (no change)
            action = f"Set ON to {target_brightness_ui}%"
        else: # cmd.state == "off"
            target_brightness_ui = 0
            action = "Set OFF"

    elif cmd.command == "toggle":
        if current_on:
            target_brightness_ui = 0
            action = "Toggle OFF"
        else:
            # When toggling ON from OFF state, set to 100%.
            # (rvc-console might try to restore previous brightness, app.py currently uses 100%)
            target_brightness_ui = 100
            action = f"Toggle ON to {target_brightness_ui}%"

    elif cmd.command == "brightness_up":
        if not current_on and current_brightness_ui == 0: # If light is off, start at 10%
            target_brightness_ui = 10
        else:
            target_brightness_ui = min(current_brightness_ui + 10, 100)
        action = f"Brightness UP to {target_brightness_ui}%"

    elif cmd.command == "brightness_down":
        target_brightness_ui = max(current_brightness_ui - 10, 0)
        action = f"Brightness DOWN to {target_brightness_ui}%"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid command: {cmd.command}")

    # --- Construct and Send CAN Message ---
    # Scale UI brightness (0-100) to CAN brightness level (0-200, capped at 0xC8 as per RV-C for 100%)
    brightness_can_level = min(target_brightness_ui * 2, 0xC8)

    # RV-C CAN ID Construction (Priority, PGN, Source Address)
    # This was confirmed to be equivalent to rvc-console.py's method for PDU2 DGNs like 0x1FEDB
    prio = 6
    sa = 0xF9 # Source Address for commands from this controller
    # pgn here is the DGN value from light_command_info (e.g., 0x1FEDB)
    arbitration_id = (prio << 26) | (pgn << 8) | sa

    # RV-C Payload for DC_DIMMER_COMMAND_2 (DGN 0x1FEDB)
    # byte 0: Instance
    # byte 1: Group Mask (0x7C for "All Instances of this DGN at this SA that support this command")
    # byte 2: Desired Level (0-200, 0xC8 = 100%)
    # byte 3: Command (0x00 = SetLevel)
    # byte 4: Duration (0x00 = Instantaneous)
    # byte 5-7: Reserved (0xFF)
    payload_data = bytes([
        instance,
        0x7C, 
        brightness_can_level, 
        0x00, # Command: SetLevel
        0x00, # Duration: Instantaneous
        0xFF, 0xFF, 0xFF # Reserved
    ])

    logging.debug(f"Preparing CAN message for entity={entity_id}: ID=0x{arbitration_id:08X}, Data={payload_data.hex().upper()}, PGN=0x{pgn:X}, Instance={instance}, Interface={interface}, TargetUIBrightness={target_brightness_ui}%, CANLevel={brightness_can_level}")
    # ... (rest of try/except block for sending remains the same) ...
    try:
        msg = can.Message(arbitration_id=arbitration_id, data=payload_data, is_extended_id=True)
        # Enqueue once. The can_writer task handles sending it twice.
        with CAN_TX_ENQUEUE_LATENCY.time():
            await can_tx_queue.put((msg, interface))
            CAN_TX_ENQUEUE_TOTAL.inc()
        CAN_TX_QUEUE_LENGTH.set(can_tx_queue.qsize()) # Update gauge after successful enqueue
        logging.info(f"Action: {action} for {entity_id} (CAN Level: {brightness_can_level}) → enqueued to {interface}")
    except Exception as e:
        logging.error(f"Failed to enqueue CAN control for {entity_id}: {e}")
        raise HTTPException(status_code=500, detail="CAN send failed")

    return {
        "status": "sent",
        "entity_id": entity_id,
        "command": cmd.command,
        "brightness": target_brightness_ui, # Return the target UI brightness
        "action": action,
    }

@app.get("/queue", response_model=dict)
async def get_queue_status():
    """
    Return the current status of the CAN transmit queue.
    """
    return {
        "length": can_tx_queue.qsize(),
        "maxsize": can_tx_queue.maxsize or "unbounded"
    }


@app.exception_handler(ResponseValidationError)
async def validation_exception_handler(request, exc):
    return PlainTextResponse(f"Validation error: {exc}", status_code=500)
