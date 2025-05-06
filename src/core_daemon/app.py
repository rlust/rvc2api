#!/usr/bin/env python3
import os
import asyncio
import json
import threading
import time
import logging
import coloredlogs
import shutil # Keep for now, though copy_config_files is removed
from typing import Dict, Any, Optional, List
from collections import deque
from pathlib import Path

import can
from can.exceptions import CanInterfaceNotImplementedError
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Query, Response, Body
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from rvc_decoder import load_config_data, decode_payload
from rvc_decoder.decode import _default_paths

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
coloredlogs.install(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    fmt="%(asctime)s %(name)s[%(process)d] %(levelname)s %(message)s"
)
logger.setLevel(logging.DEBUG) # Ensure this logger processes DEBUG messages for its handlers

logger.info("rvc2api starting up...")

# ── Determine actual config paths for core logic and UI display ────────────────
spec_override_env = os.getenv("CAN_SPEC_PATH")
mapping_override_env = os.getenv("CAN_MAP_PATH")

_decoder_default_spec_path, _decoder_default_map_path = _default_paths()

# Determine actual spec path that will be used by load_config_data and for UI
actual_spec_path_for_ui = _decoder_default_spec_path
if spec_override_env:
    if os.path.exists(spec_override_env) and os.access(spec_override_env, os.R_OK):
        actual_spec_path_for_ui = spec_override_env
    else:
        logger.warning(
            f"Override RVC Spec Path '{spec_override_env}' is missing or unreadable. "
            f"Core logic will attempt to use bundled default: '{_decoder_default_spec_path}'"
        )
        # actual_spec_path_for_ui remains _decoder_default_spec_path for UI consistency if override fails for core logic

# Determine actual mapping path that will be used by load_config_data and for UI
actual_map_path_for_ui = _decoder_default_map_path
if mapping_override_env:
    if os.path.exists(mapping_override_env) and os.access(mapping_override_env, os.R_OK):
        actual_map_path_for_ui = mapping_override_env
    else:
        logger.warning(
            f"Override Device Mapping Path '{mapping_override_env}' is missing or unreadable. "
            f"Core logic will attempt to use bundled default: '{_decoder_default_map_path}'"
        )
        # actual_map_path_for_ui remains _decoder_default_map_path for UI consistency if override fails for core logic

logger.info(f"UI will attempt to display RVC spec from: {actual_spec_path_for_ui}")
logger.info(f"UI will attempt to display device mapping from: {actual_map_path_for_ui}")

# ── Load spec & mappings for core logic ──────────────────────────────────────
# load_config_data will perform its own logging regarding path resolution
logger.info(f"Core logic attempting to load CAN spec from: {spec_override_env or '(default)'}, mapping from: {mapping_override_env or '(default)'}")
(
    decoder_map,
    raw_device_mapping,
    device_lookup,
    status_lookup,
    light_entity_ids,
    entity_id_lookup,
    light_command_info,
) = load_config_data(
    rvc_spec_path_override=spec_override_env,
    device_mapping_path_override=mapping_override_env,
)

# ── Pydantic Models for API responses ────────────────────────────────────────
class Entity(BaseModel):
    entity_id: str
    value: Dict[str, str]
    raw: Dict[str, int]
    state: str
    timestamp: float
    suggested_area: Optional[str] = "Unknown"
    device_type: Optional[str] = "unknown"
    capabilities: Optional[List[str]] = []
    friendly_name: Optional[str] = None # Added friendly_name
    location_type: Optional[str] = None # New field for interior/exterior

class ControlCommand(BaseModel):
    command: str
    state: Optional[str] = Field(None, description="Target state: 'on' or 'off'. Required only for 'set' command.")
    brightness: Optional[int] = Field(None, ge=0, le=100, description="Brightness percent (0–100). Only used when command is 'set' and state is 'on'.")

class SuggestedMapping(BaseModel):
    instance: str
    name: str
    suggested_area: Optional[str] = None

class UnmappedEntryModel(BaseModel):
    pgn_hex: str
    dgn_hex: str
    instance: str
    last_data_hex: str
    decoded_signals: Optional[Dict[str, Any]] = None
    first_seen_timestamp: float
    last_seen_timestamp: float
    count: int
    suggestions: Optional[List[SuggestedMapping]] = None # Added for suggestions

class BulkLightControlResponse(BaseModel):
    status: str
    action: str
    lights_processed: int
    lights_commanded: int
    errors: List[str] = []

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

# ── FastAPI setup ──────────────────────────────────────────────────────────
app = FastAPI(
    title="Holtel rvc2api",
    servers=[{"url": "/", "description": "Holtel de Assfire"}],
    root_path="/api" # Changed from openapi_prefix to root_path
)
web_ui_dir = os.path.join(os.path.dirname(__file__), "web_ui")
# Mount static files (if any other static assets are used, otherwise this can be removed too)
# For now, keep it and ensure the directory exists.
app.mount("/static", StaticFiles(directory=os.path.join(web_ui_dir, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(web_ui_dir, "templates"))

@app.on_event("startup")
async def ensure_static_dir_exists():
    # Ensures the /static directory for FastAPI's StaticFiles mount exists.
    # This was previously done by copy_config_files.
    static_dir_for_mount = os.path.join(web_ui_dir, "static")
    os.makedirs(static_dir_for_mount, exist_ok=True)
    logger.info(f"Ensured static directory for mount exists: {static_dir_for_mount}")

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
unmapped_entries: Dict[str, UnmappedEntryModel] = {} # Added for unmapped entries

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
                    logger.error(f"Failed to initialize CAN bus '{interface}' ({bustype}): {e}")
                    can_tx_queue.task_done()
                    continue

            try:
                bus.send(msg)
                logger.info(f"CAN TX: {interface} ID: {msg.arbitration_id:08X} Data: {msg.data.hex().upper()}") # Log first send
                await asyncio.sleep(0.05) # RV-C spec recommends sending commands twice
                bus.send(msg)
                logger.info(f"CAN TX: {interface} ID: {msg.arbitration_id:08X} Data: {msg.data.hex().upper()}") # Log second send
            except Exception as e:
                logger.error(f"CAN writer failed to send message on {interface}: {e}")
        except Exception as e:
            logger.error(f"CAN writer encountered an unexpected error for {interface}: {e}")
        finally:
            can_tx_queue.task_done()
            CAN_TX_QUEUE_LENGTH.set(can_tx_queue.qsize())

@app.on_event("startup")
async def start_can_writer():
    asyncio.create_task(can_writer())
    logger.info("CAN writer task started.")

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
    brightness = raw.get("operating_status", 0) # Changed key
    human_state = "on" if brightness > 0 else "off"
    lookup = entity_id_lookup.get(eid, {})
    payload = {
        "entity_id": eid,
        "value": decoded,
        "raw": raw,
        "state": human_state,
        "timestamp": now,
        "suggested_area": lookup.get("suggested_area", "Unknown"),
        "device_type": lookup.get("device_type", "unknown"),
        "capabilities": lookup.get("capabilities", []),
        "friendly_name": lookup.get("friendly_name"), # Ensure friendly_name is included
        "location_type": lookup.get("location_type") # Add location_type
    }
    state[eid] = payload
    history[eid].append(payload)

ENTITY_COUNT.set(len(state))
for eid in history:
    HISTORY_SIZE_GAUGE.labels(entity_id=eid).set(len(history[eid]))

# ── Active WebSocket clients ────────────────────────────────────────────────
clients: set[WebSocket] = set()

# ── Log WebSocket clients ──────────────────────────────────────────────────
log_ws_clients: set[WebSocket] = set()

# ── Log WebSocket Handler ──────────────────────────────────────────────────
class WebSocketLogHandler(logging.Handler):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop = loop

    def emit(self, record):
        log_entry = self.format(record)
        # Iterate over a copy of the set for safe removal if a client disconnects
        for ws_client in list(log_ws_clients):
            try:
                if self.loop and self.loop.is_running():
                    coro = ws_client.send_text(log_entry)
                    asyncio.run_coroutine_threadsafe(coro, self.loop)
                # else: # Loop not running or not available, log silently dropped for WS
                    # print(f"WebSocketLogHandler: Event loop not available. Dropping log: {log_entry}")
            except Exception:
                # If send_text fails (e.g., client disconnected abruptly), remove from set
                log_ws_clients.discard(ws_client)

@app.on_event("startup")
async def setup_websocket_logging():
    """Initializes and adds the WebSocketLogHandler to the root logger."""
    try:
        main_loop = asyncio.get_running_loop()
        log_ws_handler = WebSocketLogHandler(loop=main_loop)
        
        # Set level to DEBUG so it processes all messages; client-side will filter
        log_ws_handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        log_ws_handler.setFormatter(formatter)
        
        # Add to the root logger to capture logs from all modules
        logging.getLogger().addHandler(log_ws_handler)
        
        logger.info("WebSocketLogHandler initialized and added to the root logger.")
    except Exception as e:
        logger.error(f"Failed to setup WebSocket logging: {e}", exc_info=True)

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
    logger.info(f"Preparing CAN readers for interfaces: {interfaces}, bustype: {bustype}, bitrate: {bitrate}")

    for iface in interfaces:
        def reader(iface=iface):
            try:
                bus = can.interface.Bus(channel=iface, bustype=bustype, bitrate=bitrate)
                buses[iface] = bus
            except CanInterfaceNotImplementedError as e:
                logger.error(f"Cannot open CAN bus '{iface}' ({bustype}, {bitrate}bps): {e}")
                return
            except Exception as e:
                logger.error(f"Failed to initialize CAN bus '{iface}' ({bustype}, {bitrate}bps) due to an unexpected error: {e}")
                return

            logger.info(f"Started CAN reader on {iface} via {bustype} @ {bitrate}bps")
            while True:
                msg = bus.recv(timeout=1.0)
                if msg is None:
                    continue

                FRAME_COUNTER.inc()
                start_time = time.perf_counter()
                decoded_payload_for_unmapped: Optional[Dict[str, Any]] = None # Variable to hold decoded data
                entry = decoder_map.get(msg.arbitration_id)

                try:
                    if not entry:
                        LOOKUP_MISSES.inc()
                        # Store unmapped entry for unknown PGN
                        unmapped_key_str = f"PGN_UNKNOWN-{msg.arbitration_id:X}" # Ensure unique key for PGN unknown
                        now_ts = time.time()
                        pgn_hex_val = f"{(msg.arbitration_id >> 8) & 0x3FFFF:X}"

                        if unmapped_key_str not in unmapped_entries:
                            unmapped_entries[unmapped_key_str] = UnmappedEntryModel(
                                pgn_hex=pgn_hex_val,
                                dgn_hex=f"{msg.arbitration_id:X}", # Use full Arb ID as DGN placeholder
                                instance="N/A",
                                last_data_hex=msg.data.hex().upper(),
                                decoded_signals=None, # No decoded signals if PGN is unknown
                                first_seen_timestamp=now_ts,
                                last_seen_timestamp=now_ts,
                                count=1
                            )
                        else:
                            current_unmapped = unmapped_entries[unmapped_key_str]
                            current_unmapped.last_data_hex = msg.data.hex().upper()
                            current_unmapped.last_seen_timestamp = now_ts
                            current_unmapped.count += 1
                        continue # Skip further processing
                    
                    # PGN is known, attempt to decode
                    decoded, raw = decode_payload(entry, msg.data)
                    decoded_payload_for_unmapped = decoded # Store for potential unmapped entry
                    SUCCESSFUL_DECODES.inc()

                except Exception as e:
                    logger.error(f"Decode error for PGN 0x{msg.arbitration_id:X} on {iface}: {e}")
                    DECODE_ERRORS.inc()
                    continue
                finally:
                    FRAME_LATENCY.observe(time.perf_counter() - start_time)

                # At this point, PGN is known and decoded successfully
                dgn = entry.get("dgn_hex") 
                inst = raw.get("instance") # instance can be 0

                if not dgn or inst is None:
                    LOOKUP_MISSES.inc()
                    logger.debug(f"DGN or instance missing in decoded payload for PGN 0x{msg.arbitration_id:X} (Spec DGN: {entry.get('dgn_hex')}). DGN from payload: {dgn}, Instance from payload: {inst}")
                    # Potentially log this as a specific type of unmapped if DGN/Inst couldn't be derived from a known PGN's signals
                    # For now, we assume `decode_payload` populates `raw` with `instance` if the PGN spec defines it.
                    # If `dgn` from spec or `instance` from raw signals is missing, it's a config/spec issue or unexpected payload.
                    continue

                key = (dgn.upper(), str(inst))
                # Find all matching devices for this status DGN/instance
                matching_devices = [
                    dev for k, dev in status_lookup.items()
                    if k == key
                ]
                # If no match, try default instance
                if not matching_devices:
                    default_key = (dgn.upper(), "default")
                    if default_key in status_lookup:
                        matching_devices = [status_lookup[default_key]]
                # Fallback to device_lookup if still not found
                if not matching_devices:
                    if key in device_lookup:
                        matching_devices = [device_lookup[key]]
                    elif (dgn.upper(), "default") in device_lookup:
                        matching_devices = [device_lookup[(dgn.upper(), "default")]]

                if not matching_devices:
                    LOOKUP_MISSES.inc()
                    logger.debug(f"No device config for DGN={dgn}, Inst={inst} (PGN 0x{msg.arbitration_id:X})")

                    unmapped_key_str = f"{dgn.upper()}-{str(inst)}"
                    pgn_from_entry = entry.get("pgn_hex", f"{(msg.arbitration_id >> 8) & 0x3FFFF:X}")
                    now_ts = time.time()

                    # Generate suggestions
                    suggestions_list = []
                    if raw_device_mapping and isinstance(raw_device_mapping.get("devices"), list):
                        for device_config in raw_device_mapping["devices"]:
                            if device_config.get("dgn_hex", "").upper() == dgn.upper() and str(device_config.get("instance")) != str(inst):
                                suggestions_list.append(SuggestedMapping(
                                    instance=str(device_config.get("instance")),
                                    name=device_config.get("name", "Unknown Name"),
                                    suggested_area=device_config.get("suggested_area")
                                ))

                    if unmapped_key_str not in unmapped_entries:
                        unmapped_entries[unmapped_key_str] = UnmappedEntryModel(
                            pgn_hex=pgn_from_entry,
                            dgn_hex=dgn.upper(),
                            instance=str(inst),
                            last_data_hex=msg.data.hex().upper(),
                            decoded_signals=decoded_payload_for_unmapped, # Store the decoded signals
                            first_seen_timestamp=now_ts,
                            last_seen_timestamp=now_ts,
                            count=1,
                            suggestions=suggestions_list if suggestions_list else None
                        )
                    else:
                        current_unmapped = unmapped_entries[unmapped_key_str]
                        current_unmapped.last_data_hex = msg.data.hex().upper()
                        current_unmapped.decoded_signals = decoded_payload_for_unmapped # Update decoded signals
                        current_unmapped.last_seen_timestamp = now_ts
                        current_unmapped.count += 1
                        # Update suggestions if they weren't there or if logic changes (optional)
                        if not current_unmapped.suggestions and suggestions_list:
                            current_unmapped.suggestions = suggestions_list
                    continue

                ts = time.time()
                raw_brightness = raw.get("operating_status", 0)
                state_str = "on" if raw_brightness > 0 else "off"

                for device in matching_devices:
                    eid = device["entity_id"]
                    lookup = entity_id_lookup.get(eid, {}) # Get full lookup for additional fields
                    payload = {
                        "entity_id": eid,
                        "value": decoded,
                        "raw": raw,
                        "state": state_str,
                        "timestamp": ts,
                        "suggested_area": lookup.get("suggested_area", "Unknown"),
                        "device_type": lookup.get("device_type", "unknown"),
                        "capabilities": lookup.get("capabilities", []),
                        "friendly_name": lookup.get("friendly_name"), # Add friendly_name
                        "location_type": lookup.get("location_type") # Add location_type
                    }
                    # Custom Metrics
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
@app.get("/entities", response_model=Dict[str, Entity]) # Removed /api/ prefix
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

@app.get("/entities/ids", response_model=List[str]) # Removed /api/ prefix
async def list_entity_ids():
    """Return all known entity IDs."""
    return list(state.keys())

@app.get("/entities/{entity_id}", response_model=Entity) # Removed /api/ prefix
async def get_entity(entity_id: str):
    """Return the latest value for one entity."""
    ent = state.get(entity_id)
    if not ent:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ent

@app.get("/entities/{entity_id}/history", response_model=List[Entity]) # Removed /api/ prefix
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

@app.get("/unmapped_entries", response_model=Dict[str, UnmappedEntryModel]) # Removed /api/ prefix
async def get_unmapped_entries():
    """
    Return all DGN/instance pairs that were seen on the bus but not mapped in device_mapping.yml.
    Stores the last seen data payload for each and provides suggestions based on existing mappings.
    """
    # The suggestions are now added when the unmapped entry is first created or updated.
    # So, we can just return the unmapped_entries dictionary as is.
    return unmapped_entries

@app.get("/lights", response_model=Dict[str, Entity]) # Removed /api/ prefix
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
        # Ensure only device_type 'light' is included
        if cfg.get("device_type") != "light":
            continue
        if area and cfg.get("suggested_area") != area:
            continue
        caps = cfg.get("capabilities", [])
        if capability and capability not in caps:
            continue
        if state_filter:
            val = ent.get("state")
            if not val or val.strip().lower() != state_filter.strip().lower():
                continue
        results[eid] = {
            **ent,
            "suggested_area": cfg.get("suggested_area", "Unknown"),
            "device_type": cfg.get("device_type", "unknown"),
            "capabilities": cfg.get("capabilities", []),
            "friendly_name": cfg.get("friendly_name", None),
            "location_type": cfg.get("location_type", None), # Add location_type
        }
    return results

@app.get("/meta", response_model=Dict[str, List[str]]) # Removed /api/ prefix
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
    # Add location_type to meta if you want to filter by it directly in the future
    location_types = set()
    for cfg in entity_id_lookup.values():
        lt = cfg.get("location_type")
        if lt:
            location_types.add(lt)
    out["location_type"] = sorted(location_types)


    return out

@app.get("/healthz") # Removed /api/ prefix
async def healthz():
    """Liveness probe."""
    return JSONResponse(status_code=200, content={"status": "ok"})

@app.get("/readyz") # Removed /api/ prefix
async def readyz():
    """
    Readiness probe: 200 once at least one frame decoded, else 503.
    """
    ready = len(state) > 0
    code = 200 if ready else 503
    return JSONResponse(status_code=code, content={"status": "ready" if ready else "pending", "entities": len(state)})

@app.get("/metrics") # Removed /api/ prefix
def metrics():
    """Prometheus metrics endpoint."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

@app.get("/config/device_mapping", response_class=PlainTextResponse) # Removed /api/ prefix
async def get_device_mapping_config_content_api():
    # Serves the content of the device mapping file that the application is effectively using.
    if os.path.exists(actual_map_path_for_ui):
        try:
            with open(actual_map_path_for_ui, 'r') as f:
                return PlainTextResponse(f.read())
        except Exception as e:
            logger.error(f"API Error: Could not read device mapping from '{actual_map_path_for_ui}': {e}")
            raise HTTPException(status_code=500, detail=f"Error reading device mapping file: {str(e)}")
    else:
        logger.error(f"API Error: Device mapping file not found for UI display at '{actual_map_path_for_ui}'")
        raise HTTPException(status_code=404, detail="Device mapping file not found.")

CONFIG_PATH = Path(__file__).parent / "rvc_decoder" / "config"
RVC_SPEC_FILE = CONFIG_PATH / "rvc.json"
DEVICE_MAPPING_FILE = CONFIG_PATH / "device_mapping.yml"

@app.get("/config/rvc_spec_details")
async def get_rvc_spec_details():
    """Returns metadata from the rvc.json spec file."""
    try:
        with open(RVC_SPEC_FILE, 'r') as f:
            spec_data = json.load(f)
        return {
            "version": spec_data.get("version"),
            "spec_document": spec_data.get("spec_document")
        }
    except FileNotFoundError:
        logger.error(f"rvc.json not found at {RVC_SPEC_FILE}")
        raise HTTPException(status_code=404, detail="rvc.json not found")
    except json.JSONDecodeError:
        logger.error(f"Error decoding rvc.json at {RVC_SPEC_FILE}")
        raise HTTPException(status_code=500, detail="Error decoding rvc.json")

@app.get("/config/rvc_spec_metadata")
async def get_rvc_spec_metadata():
    """Returns metadata (version and spec_document URL) from the rvc.json spec file."""
    if not os.path.exists(actual_spec_path_for_ui):
        logger.error(f"API Error: RVC spec file not found at '{actual_spec_path_for_ui}' for metadata endpoint")
        raise HTTPException(status_code=404, detail="RVC spec file not found.")
    try:
        with open(actual_spec_path_for_ui, 'r') as f:
            spec_data = json.load(f)
        return {
            "version": spec_data.get("version"),
            "spec_document": spec_data.get("spec_document")
        }
    except json.JSONDecodeError:
        logger.error(f"API Error: Could not decode RVC spec from '{actual_spec_path_for_ui}'")
        raise HTTPException(status_code=500, detail="Error decoding RVC spec file.")
    except Exception as e:
        logger.error(f"API Error: Could not read RVC spec from '{actual_spec_path_for_ui}': {e}")
        raise HTTPException(status_code=500, detail=f"Error reading RVC spec file: {str(e)}")

@app.get("/config/rvc_spec", response_class=PlainTextResponse) # Removed /api/ prefix
async def get_rvc_spec_config_content_api():
    # Serves the content of the RVC spec file that the application is effectively using.
    if os.path.exists(actual_spec_path_for_ui):
        try:
            with open(actual_spec_path_for_ui, 'r') as f:
                return PlainTextResponse(f.read())
        except Exception as e:
            logger.error(f"API Error: Could not read RVC spec from '{actual_spec_path_for_ui}': {e}")
            raise HTTPException(status_code=500, detail=f"Error reading RVC spec file: {str(e)}")
    else:
        logger.error(f"API Error: RVC spec file not found for UI display at '{actual_spec_path_for_ui}'")
        raise HTTPException(status_code=404, detail="RVC spec file not found.")

@app.websocket("/ws") # Removed /api/ prefix
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket endpoint: push every new payload as JSON.
    """
    await ws.accept()
    clients.add(ws)
    WS_CLIENTS.set(len(clients))
    logger.info(f"WebSocket client connected: {ws.client.host}:{ws.client.port}")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.discard(ws)
        WS_CLIENTS.set(len(clients))
        logger.info(f"WebSocket client disconnected: {ws.client.host}:{ws.client.port}")
    except Exception as e:
        clients.discard(ws)
        WS_CLIENTS.set(len(clients))
        logger.error(f"WebSocket error for client {ws.client.host}:{ws.client.port}: {e}")

@app.websocket("/ws/logs") # Removed /api/ prefix
async def websocket_logs(ws: WebSocket):
    """
    WebSocket endpoint: stream all log messages in real time.
    """
    await ws.accept()
    log_ws_clients.add(ws)
    logger.info(f"Log WebSocket client connected: {ws.client.host}:{ws.client.port}")
    try:
        while True:
            await ws.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        log_ws_clients.discard(ws)
        logger.info(f"Log WebSocket client disconnected: {ws.client.host}:{ws.client.port}")
    except Exception as e:
        log_ws_clients.discard(ws)
        logger.error(f"Log WebSocket error for client {ws.client.host}:{ws.client.port}: {e}")

async def _send_light_can_command(
    entity_id: str,
    target_brightness_ui: int, # 0-100
    action_description: str
) -> bool:
    """
    Helper function to construct, send a CAN command for a light, and perform optimistic update.
    Returns True if the command was successfully queued, False otherwise.
    """
    if entity_id not in light_command_info:
        logger.error(f"Control Error: {entity_id} not found in light_command_info for action '{action_description}'.")
        return False

    info = light_command_info[entity_id]
    pgn = info["dgn"]
    instance = info["instance"]
    interface = info["interface"]

    # Scale UI brightness (0-100) to CAN brightness level (0-200, capped at 0xC8 as per RV-C for 100%)
    brightness_can_level = min(target_brightness_ui * 2, 0xC8)

    prio = 6
    sa = 0xF9
    dp = (pgn >> 16) & 1
    pf = (pgn >> 8) & 0xFF
    da = 0xFF

    if (pf < 0xF0):
        arbitration_id = (prio << 26) | (dp << 24) | (pf << 16) | (da << 8) | sa
    else:
        ps = pgn & 0xFF
        arbitration_id = (prio << 26) | (dp << 24) | (pf << 16) | (ps << 8) | sa

    payload_data = bytes([
        instance,
        0x7C, # Group Mask
        brightness_can_level,
        0x00, # Command: SetLevel
        0x00, # Duration: Instantaneous
        0xFF, 0xFF, 0xFF
    ])

    logger.info(f"CAN CMD OUT (Helper): entity_id={entity_id}, arbitration_id=0x{arbitration_id:08X}, data={payload_data.hex().upper()}, instance={instance}, action='{action_description}'")

    try:
        msg = can.Message(arbitration_id=arbitration_id, data=payload_data, is_extended_id=True)
        with CAN_TX_ENQUEUE_LATENCY.time():
            await can_tx_queue.put((msg, interface))
            CAN_TX_ENQUEUE_TOTAL.inc()
        CAN_TX_QUEUE_LENGTH.set(can_tx_queue.qsize())
        logger.info(f"CAN CMD Queued (Helper): '{action_description}' for {entity_id} (CAN Lvl: {brightness_can_level}) -> {interface}")

        # Optimistic State Update
        optimistic_state_str = "on" if target_brightness_ui > 0 else "off"
        optimistic_raw_val = {"operating_status": brightness_can_level, "instance": instance, "group": 0x7C}
        optimistic_value_val = {"operating_status": str(brightness_can_level), "instance": str(instance), "group": str(0x7C)}
        ts = time.time()
        lookup = entity_id_lookup.get(entity_id, {})
        
        current_payload = state.get(entity_id, {}).copy() # Get current state to preserve other fields
        current_payload.update({
            "entity_id": entity_id, # Ensure entity_id is present
            "value": optimistic_value_val,
            "raw": optimistic_raw_val,
            "state": optimistic_state_str,
            "timestamp": ts,
            # Preserve existing fields if not updated by this command type
            "suggested_area": lookup.get("suggested_area", current_payload.get("suggested_area", "Unknown")),
            "device_type": lookup.get("device_type", current_payload.get("device_type", "light")),
            "capabilities": lookup.get("capabilities", current_payload.get("capabilities", [])),
            "friendly_name": lookup.get("friendly_name", current_payload.get("friendly_name")),
            "location_type": lookup.get("location_type", current_payload.get("location_type"))
        })
        state[entity_id] = current_payload # Update state with the merged payload

        if entity_id in history: # Ensure history deque exists
            history[entity_id].append(current_payload)
            cutoff = ts - HISTORY_DURATION
            while history[entity_id] and history[entity_id][0]["timestamp"] < cutoff:
                history[entity_id].popleft()
            HISTORY_SIZE_GAUGE.labels(entity_id=entity_id).set(len(history[entity_id]))
        else: # Should not happen if pre-seeded correctly
            logger.warning(f"History deque not found for {entity_id} during optimistic update.")

        ENTITY_COUNT.set(len(state))
        text = json.dumps(current_payload)
        await broadcast_to_clients(text)
        return True
    except Exception as e:
        logger.error(f"Failed to enqueue or optimistically update CAN control for {entity_id} (Action: '{action_description}'): {e}", exc_info=True)
        return False

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
        logger.debug(f"Control command for unknown entity_id: {entity_id}")
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity_id not in light_command_info:
        logger.debug(f"Control command for non-controllable entity_id: {entity_id}")
        raise HTTPException(status_code=400, detail="Entity is not controllable")

    logger.info(f"HTTP CMD RX: entity_id='{entity_id}', command='{cmd.command}', state='{cmd.state}', brightness='{cmd.brightness}'")

    info = light_command_info[entity_id]
    pgn = info["dgn"] # This is the PGN, e.g., 0x1FEDB for DC_DIMMER_COMMAND_2
    instance = info["instance"]
    interface = info["interface"]

    # --- Read Current State ---
    current_state_data = state.get(entity_id, {})

    # Determine current_on using the reader's pre-calculated "state" field
    current_on_str = current_state_data.get("state", "off") # Default to "off" if not found
    current_on = current_on_str.lower() == "on"

    logger.debug(f"Control for {entity_id}: current_on_str='{current_on_str}', current_on={current_on}")

    # Determine current_brightness_ui using the correct signal name from raw data
    current_raw_values = current_state_data.get("raw", {})
    # The reader thread in app.py uses "operating_status" to determine its "state" field.
    # We rely on that key for the current raw brightness value.
    # Assuming raw 0-200 maps to UI 0-100%
    current_brightness_raw = current_raw_values.get("operating_status", 0) # Changed key. Default to 0 if key not found
    
    current_brightness_ui = 0
    # Ensure raw value is treated as a number, scale it to UI percentage (0-100)
    if isinstance(current_brightness_raw, (int, float)):
        current_brightness_ui = min(int(current_brightness_raw) // 2, 100)
    
    logger.debug(f"Control for {entity_id}: current_brightness_raw='{current_brightness_raw}', current_brightness_ui={current_brightness_ui}%")
    
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

    # --- Use Helper to Send CAN Message and Update State ---
    if not await _send_light_can_command(entity_id, target_brightness_ui, action):
        raise HTTPException(status_code=500, detail=f"Failed to send CAN command for {entity_id} (Action: {action})")

    return {
        "status": "sent", # Or "queued"
        "entity_id": entity_id,
        "command": cmd.command,
        "brightness": target_brightness_ui,
        "action": action,
    }

# --- Bulk Light Control Endpoints ---
async def _bulk_control_lights(
    location_filter: Optional[str], # "interior", "exterior", or None for "all"
    target_state_on: bool, # True for ON, False for OFF
    action_name: str
) -> BulkLightControlResponse:
    lights_processed = 0
    lights_commanded = 0
    errors = []
    
    target_brightness_ui = 100 if target_state_on else 0
    action_verb = "ON" if target_state_on else "OFF"

    for eid in light_entity_ids:
        device_config = entity_id_lookup.get(eid, {})
        if device_config.get("device_type") != "light":
            continue # Skip non-light devices

        lights_processed += 1
        
        if location_filter:
            if device_config.get("location_type") != location_filter:
                continue # Skip if location doesn't match

        action_description = f"Bulk: {action_name} {action_verb} - {eid}"
        if eid not in light_command_info:
            logger.warning(f"{action_description}: Skipped, not in light_command_info.")
            errors.append(f"{eid}: Not controllable (missing command info)")
            continue

        if await _send_light_can_command(eid, target_brightness_ui, action_description):
            lights_commanded += 1
        else:
            errors.append(f"{eid}: Failed to send command")
            
    return BulkLightControlResponse(
        status="completed",
        action=f"{action_name} {action_verb}",
        lights_processed=lights_processed,
        lights_commanded=lights_commanded,
        errors=errors
    )

@app.post("/lights/all/on", response_model=BulkLightControlResponse)
async def lights_all_on():
    return await _bulk_control_lights(None, True, "All Lights")

@app.post("/lights/all/off", response_model=BulkLightControlResponse)
async def lights_all_off():
    return await _bulk_control_lights(None, False, "All Lights")

@app.post("/lights/interior/on", response_model=BulkLightControlResponse)
async def lights_interior_on():
    return await _bulk_control_lights("interior", True, "Interior Lights")

@app.post("/lights/interior/off", response_model=BulkLightControlResponse)
async def lights_interior_off():
    return await _bulk_control_lights("interior", False, "Interior Lights")

@app.post("/lights/exterior/on", response_model=BulkLightControlResponse)
async def lights_exterior_on():
    return await _bulk_control_lights("exterior", True, "Exterior Lights")

@app.post("/lights/exterior/off", response_model=BulkLightControlResponse)
async def lights_exterior_off():
    return await _bulk_control_lights("exterior", False, "Exterior Lights")

@app.get("/queue", response_model=dict) # Removed /api/ prefix
async def get_queue_status():
    """
    Return the current status of the CAN transmit queue.
    """
    return {
        "length": can_tx_queue.qsize(),
        "maxsize": can_tx_queue.maxsize or "unbounded"
    }

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("rvc2api shutting down...")

@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.exception_handler(ResponseValidationError)
async def validation_exception_handler(request, exc):
    return PlainTextResponse(f"Validation error: {exc}", status_code=500)
