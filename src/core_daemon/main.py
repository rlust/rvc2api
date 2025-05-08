#!/usr/bin/env python3
import asyncio
import functools  # Added for functools.partial
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import can
import uvicorn  # Added for main()
from fastapi import Body, FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

# Import application state variables and initialization function
from core_daemon.app_state import get_last_known_brightness  # Added import
from core_daemon.app_state import preseed_light_states  # Import the pre-seeding function
from core_daemon.app_state import set_last_known_brightness  # Added import
from core_daemon.app_state import (  # Import the new state update function
    history,
    initialize_history_deques,
    state,
    unmapped_entries,
    update_entity_state_and_history,
)

# Import CAN components from can_manager
from core_daemon.can_manager import can_tx_queue  # Shared CAN transmit queue
from core_daemon.can_manager import initialize_can_writer_task  # Function to start the CAN writer
from core_daemon.can_manager import create_light_can_message, initialize_can_listeners
from core_daemon.config import (
    configure_logger,
    get_actual_paths,
    get_canbus_config,
    get_fastapi_config,
    get_static_paths,
)
from core_daemon.metrics import (
    CAN_TX_ENQUEUE_LATENCY,
    CAN_TX_ENQUEUE_TOTAL,
    CAN_TX_QUEUE_LENGTH,
    DECODE_ERRORS,
    DGN_TYPE_GAUGE,
    FRAME_COUNTER,
    FRAME_LATENCY,
    GENERATOR_COMMAND_COUNTER,
    GENERATOR_DEMAND_COMMAND_COUNTER,
    GENERATOR_STATUS_1_COUNTER,
    GENERATOR_STATUS_2_COUNTER,
    HTTP_LATENCY,
    HTTP_REQUESTS,
    INST_USAGE_COUNTER,
    LOOKUP_MISSES,
    PGN_USAGE_COUNTER,
    SUCCESSFUL_DECODES,
)
from core_daemon.models import (
    BulkLightControlResponse,
    ControlCommand,
    ControlEntityResponse,
    Entity,
    SuggestedMapping,
    UnmappedEntryModel,
)
from core_daemon.websocket import (
    WebSocketLogHandler,
    broadcast_to_clients,
    websocket_endpoint,
    websocket_logs_endpoint,
)
from rvc_decoder import decode_payload, load_config_data

# ── Logging ──────────────────────────────────────────────────────────────────
logger = configure_logger()

logger.info("rvc2api starting up...")

# ── Determine actual config paths for core logic and UI display ────────────────
actual_spec_path_for_ui, actual_map_path_for_ui = get_actual_paths()

# The following logs are now redundant as get_actual_paths() in config.py logs them.
# logger.info(f"UI will attempt to display RVC spec from: {actual_spec_path_for_ui}")
# logger.info(f"UI will attempt to display device mapping from: {actual_map_path_for_ui}")

# ── Load spec & mappings for core logic ──────────────────────────────────────
# load_config_data will perform its own logging regarding path resolution
logger.info(
    "Core logic attempting to load CAN spec from: %s, mapping from: %s",
    os.getenv("CAN_SPEC_PATH") or "(default)",
    os.getenv("CAN_MAP_PATH") or "(default)",
)
(
    decoder_map,
    raw_device_mapping,
    device_lookup,
    status_lookup,
    light_entity_ids,
    entity_id_lookup,
    light_command_info,
    pgn_hex_to_name_map,  # Unpack the new map
) = load_config_data(
    rvc_spec_path_override=os.getenv("CAN_SPEC_PATH"),
    device_mapping_path_override=os.getenv("CAN_MAP_PATH"),
)

# Initialize history deques after entity_id_lookup is populated
initialize_history_deques(entity_id_lookup)

# Call the new pre-seeding function from app_state.py
preseed_light_states(
    light_entity_ids=light_entity_ids,
    light_command_info=light_command_info,
    decoder_map_values=list(decoder_map.values()),  # Pass decoder_map.values()
    entity_id_lookup=entity_id_lookup,
    decode_payload_func=decode_payload,  # Pass the actual decode_payload function
)

# Removed the manual creation of pgn_hex_to_name_map as it's now returned by load_config_data

# ── Pydantic Models for API responses ────────────────────────────────────────
# Models are now defined in core_daemon.models.py

# ── FastAPI setup ──────────────────────────────────────────────────────────
# Get FastAPI configuration
fastapi_config = get_fastapi_config()
API_TITLE = fastapi_config["title"]
API_SERVER_DESCRIPTION = fastapi_config["server_description"]
API_ROOT_PATH = fastapi_config["root_path"]

logger.info(f"API Title: {API_TITLE}")
logger.info(f"API Server Description: {API_SERVER_DESCRIPTION}")
logger.info(f"API Root Path: {API_ROOT_PATH}")

app = FastAPI(
    title=API_TITLE,
    servers=[{"url": "/", "description": API_SERVER_DESCRIPTION}],  # URL is relative to root_path
    root_path=API_ROOT_PATH,
)

# Get static and template paths
static_paths = get_static_paths()
web_ui_dir = static_paths["web_ui_dir"]
static_dir = static_paths["static_dir"]
templates_dir = static_paths["templates_dir"]

# Mount static files and templates
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)


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
# These variables are now imported from core_daemon.app_state.py
# state: Dict[str, Dict[str, Any]] = {}
# HISTORY_DURATION = 24 * 3600  # seconds
# history: Dict[str, deque[Dict[str, Any]]] = {eid: deque() for eid in entity_id_lookup}
# unmapped_entries: Dict[str, UnmappedEntryModel] = {} # Added for unmapped entries

# ── Active CAN buses ─────────────────────────────────────────────────────────
# 'buses' dictionary is now imported from can_manager.py

# ── CAN Transmit Queue ───────────────────────────────────────────────────────
# 'can_tx_queue' is now imported from can_manager.py

# Removed can_writer async function (now in can_manager.py)


@app.on_event("startup")
async def start_can_writer():
    # Call the imported function to initialize and start the CAN writer task
    initialize_can_writer_task()
    # logger.info("CAN writer task started.") # Logging is now handled by initialize_can_writer_task


# ── WebSocket components are now in core_daemon.websocket ───────────────────
# Imports moved to the top of the file


# setup_websocket_logging now uses imported components
@app.on_event("startup")
async def setup_websocket_logging():
    """Initializes and adds the WebSocketLogHandler to the root logger."""
    try:
        main_loop = asyncio.get_running_loop()
        # Use WebSocketLogHandler and log_ws_clients from websocket.py
        log_ws_handler = WebSocketLogHandler(loop=main_loop)

        log_ws_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        log_ws_handler.setFormatter(formatter)
        logging.getLogger().addHandler(log_ws_handler)
        logger.info("WebSocketLogHandler initialized and added to the root logger.")
    except Exception as e:
        logger.error(f"Failed to setup WebSocket logging: {e}", exc_info=True)


# ── CAN Message Processing Callback ──────────────────────────────────────────


def _process_can_message(msg: can.Message, iface_name: str, loop: asyncio.AbstractEventLoop):
    """
    Callback function to process a single CAN message.
    This function is called by the CAN listener threads for each message received.
    It contains the logic previously in the main read loop of `reader_thread_target`.
    """
    # Increment generator-specific counters
    if msg.arbitration_id == 536861658:  # GENERATOR_COMMAND
        GENERATOR_COMMAND_COUNTER.inc()
    elif msg.arbitration_id == 436198557:  # GENERATOR_STATUS_1
        GENERATOR_STATUS_1_COUNTER.inc()
    elif msg.arbitration_id == 536861659:  # GENERATOR_STATUS_2
        GENERATOR_STATUS_2_COUNTER.inc()
    elif msg.arbitration_id == 536870895:  # GENERATOR_DEMAND_COMMAND
        GENERATOR_DEMAND_COMMAND_COUNTER.inc()

    FRAME_COUNTER.inc()
    start_time = time.perf_counter()
    decoded_payload_for_unmapped: Optional[Dict[str, Any]] = None
    entry = decoder_map.get(msg.arbitration_id)

    try:
        if not entry:
            LOOKUP_MISSES.inc()
            # Store unmapped entry for unknown PGN
            unmapped_key_str = f"PGN_UNKNOWN-{msg.arbitration_id:X}"
            now_ts = time.time()

            model_pgn_hex = f"{(msg.arbitration_id >> 8) & 0x3FFFF:X}".upper()
            model_pgn_name = pgn_hex_to_name_map.get(model_pgn_hex)
            model_dgn_hex = f"{msg.arbitration_id:X}"
            model_dgn_name = pgn_hex_to_name_map.get(model_dgn_hex)

            if unmapped_key_str not in unmapped_entries:
                unmapped_entries[unmapped_key_str] = UnmappedEntryModel(
                    pgn_hex=model_pgn_hex,
                    pgn_name=model_pgn_name,
                    dgn_hex=model_dgn_hex,
                    dgn_name=model_dgn_name,
                    instance="N/A",
                    last_data_hex=msg.data.hex().upper(),
                    decoded_signals=None,
                    first_seen_timestamp=now_ts,
                    last_seen_timestamp=now_ts,
                    count=1,
                    spec_entry=None,
                )
            else:
                current_unmapped = unmapped_entries[unmapped_key_str]
                current_unmapped.last_data_hex = msg.data.hex().upper()
                current_unmapped.last_seen_timestamp = now_ts
                current_unmapped.count += 1
                if model_pgn_name and not current_unmapped.pgn_name:
                    current_unmapped.pgn_name = model_pgn_name
            return  # Exit processing for this message

        # PGN is known, attempt to decode
        decoded, raw = decode_payload(entry, msg.data)
        decoded_payload_for_unmapped = decoded
        SUCCESSFUL_DECODES.inc()

    except Exception as e:
        logger.error(
            f"Decode error for PGN 0x{msg.arbitration_id:X} on {iface_name}: {e}",
            exc_info=True,
        )
        DECODE_ERRORS.inc()
        return  # Exit processing for this message
    finally:
        FRAME_LATENCY.observe(time.perf_counter() - start_time)

    # At this point, PGN is known and decoded successfully
    dgn = entry.get("dgn_hex")
    inst = raw.get("instance")

    if not dgn or inst is None:
        LOOKUP_MISSES.inc()
        logger.debug(
            f"DGN or instance missing in decoded payload for PGN "
            f"0x{msg.arbitration_id:X} (Spec DGN: {entry.get('dgn_hex')}). "
            f"DGN from payload: {dgn}, Instance from payload: {inst}"
        )
        return  # Exit processing for this message

    key = (dgn.upper(), str(inst))
    matching_devices = [dev for k, dev in status_lookup.items() if k == key]
    if not matching_devices:
        default_key = (dgn.upper(), "default")
        if default_key in status_lookup:
            matching_devices = [status_lookup[default_key]]
    if not matching_devices:
        if key in device_lookup:
            matching_devices = [device_lookup[key]]
        elif (dgn.upper(), "default") in device_lookup:
            matching_devices = [device_lookup[(dgn.upper(), "default")]]

    if not matching_devices:
        LOOKUP_MISSES.inc()
        logger.debug(
            f"No device config for DGN={dgn}, Inst={inst} " f"(PGN 0x{msg.arbitration_id:X})"
        )

        unmapped_key_str = f"{dgn.upper()}-{str(inst)}"
        model_pgn_hex = f"{(msg.arbitration_id >> 8) & 0x3FFFF:X}".upper()
        model_pgn_name = pgn_hex_to_name_map.get(model_pgn_hex)
        model_dgn_hex = dgn.upper()
        model_dgn_name = entry.get("name")
        now_ts = time.time()
        suggestions_list = []
        if raw_device_mapping and isinstance(raw_device_mapping.get("devices"), list):
            for device_config in raw_device_mapping["devices"]:
                if device_config.get("dgn_hex", "").upper() == dgn.upper() and str(
                    device_config.get("instance")
                ) != str(inst):
                    suggestions_list.append(
                        SuggestedMapping(
                            instance=str(device_config.get("instance")),
                            name=device_config.get("name", "Unknown Name"),
                            suggested_area=device_config.get("suggested_area"),
                        )
                    )

        if unmapped_key_str not in unmapped_entries:
            unmapped_entries[unmapped_key_str] = UnmappedEntryModel(
                pgn_hex=model_pgn_hex,
                pgn_name=model_pgn_name,
                dgn_hex=model_dgn_hex,
                dgn_name=model_dgn_name,
                instance=str(inst),
                last_data_hex=msg.data.hex().upper(),
                decoded_signals=decoded_payload_for_unmapped,
                first_seen_timestamp=now_ts,
                last_seen_timestamp=now_ts,
                count=1,
                suggestions=suggestions_list if suggestions_list else None,
                spec_entry=entry,
            )
        else:
            current_unmapped = unmapped_entries[unmapped_key_str]
            current_unmapped.last_data_hex = msg.data.hex().upper()
            current_unmapped.decoded_signals = decoded_payload_for_unmapped
            current_unmapped.last_seen_timestamp = now_ts
            current_unmapped.count += 1
            if model_pgn_name and not current_unmapped.pgn_name:
                current_unmapped.pgn_name = model_pgn_name
            if model_dgn_name and not current_unmapped.dgn_name:
                current_unmapped.dgn_name = model_dgn_name
            if entry and not current_unmapped.spec_entry:
                current_unmapped.spec_entry = entry
            if not current_unmapped.suggestions and suggestions_list:
                current_unmapped.suggestions = suggestions_list
        return  # Exit processing for this message

    ts = time.time()
    raw_brightness = raw.get("operating_status", 0)
    state_str = "on" if raw_brightness > 0 else "off"

    for device in matching_devices:
        eid = device["entity_id"]
        lookup_data = entity_id_lookup.get(eid, {})
        payload = {
            "entity_id": eid,
            "value": decoded,
            "raw": raw,
            "state": state_str,
            "timestamp": ts,
            "suggested_area": lookup_data.get("suggested_area", "Unknown"),
            "device_type": lookup_data.get("device_type", "unknown"),
            "capabilities": lookup_data.get("capabilities", []),
            "friendly_name": lookup_data.get("friendly_name"),
            "groups": lookup_data.get("groups", []),
        }
        # Custom Metrics
        pgn_val = msg.arbitration_id & 0x3FFFF  # Corrected: pgn was msg.arbitration_id & 0x3FFFF
        PGN_USAGE_COUNTER.labels(
            pgn=f"{pgn_val:X}"
        ).inc()  # Corrected: pgn was msg.arbitration_id & 0x3FFFF
        INST_USAGE_COUNTER.labels(dgn=dgn.upper(), instance=str(inst)).inc()
        device_type = device.get("device_type", "unknown")
        DGN_TYPE_GAUGE.labels(device_type=device_type).set(1)

        # Update state and history using the centralized function
        update_entity_state_and_history(eid, payload)

        text = json.dumps(payload)
        if loop and loop.is_running():
            target_coro = broadcast_to_clients(text)
            loop.call_soon_threadsafe(loop.create_task, target_coro)

        SUCCESSFUL_DECODES.inc()


# ── CAN Reader Startup ──────────────────────────────────────────────────────
@app.on_event("startup")
async def start_can_readers():
    loop = asyncio.get_running_loop()
    canbus_config = get_canbus_config()
    interfaces = canbus_config["channels"]
    bustype = canbus_config["bustype"]
    bitrate = canbus_config["bitrate"]

    # Create a handler that bundles the _process_can_message callback with the event loop
    message_handler_with_loop = functools.partial(_process_can_message, loop=loop)

    # Initialize CAN listeners using the function from can_manager
    initialize_can_listeners(
        interfaces=interfaces,
        bustype=bustype,
        bitrate=bitrate,
        message_handler_callback=message_handler_with_loop,
        logger_instance=logger,  # Pass the configured logger instance
    )
    # The old reader_thread_target and threading.Thread creation logic is now removed
    # and handled by initialize_can_listeners in can_manager.py


# ── REST Endpoints ─────────────────────────────────────────────────────────
@app.get("/entities", response_model=Dict[str, Entity])  # Removed /api/ prefix
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


@app.get("/entities/ids", response_model=List[str])  # Removed /api/ prefix
async def list_entity_ids():
    """Return all known entity IDs."""
    return list(state.keys())


@app.get("/entities/{entity_id}", response_model=Entity)  # Removed /api/ prefix
async def get_entity(entity_id: str):
    """Return the latest value for one entity."""
    ent = state.get(entity_id)
    if not ent:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ent


@app.get("/entities/{entity_id}/history", response_model=List[Entity])  # Removed /api/ prefix
async def get_history(
    entity_id: str,
    since: Optional[float] = Query(
        None, description="Unix timestamp; only entries newer than this"
    ),
    limit: Optional[int] = Query(1000, ge=1, description="Max number of points to return"),
):
    if entity_id not in history:
        raise HTTPException(status_code=404, detail="Entity not found")
    entries = list(history[entity_id])
    if since is not None:
        entries = [e for e in entries if e["timestamp"] > since]

    # FastAPI Query provides a default, so limit should be int.
    # This reassures MyPy about Optional[int] for the unary minus in slicing.
    actual_limit = limit if limit is not None else 1000
    return entries[-actual_limit:]


@app.get("/unmapped_entries", response_model=Dict[str, UnmappedEntryModel])  # Removed /api/ prefix
async def get_unmapped_entries():
    """
    Return all DGN/instance pairs that were seen on the bus but not mapped in device_mapping.yml.
    Stores the last seen data payload for each and provides suggestions based on existing mappings.
    """
    # The suggestions are now added when the unmapped entry is first created or updated.
    # So, we can just return the unmapped_entries dictionary as is.
    return unmapped_entries


@app.get("/lights", response_model=Dict[str, Entity])  # Removed /api/ prefix
async def list_lights(
    state_filter: Optional[str] = Query(None, alias="state", description="Filter by 'on'/'off'"),
    capability: Optional[str] = Query(None, description="e.g. 'brightness' or 'on_off'"),
    area: Optional[str] = Query(None),
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
        # Construct Entity from ent, which should conform to Entity structure
        # The existing ent already contains suggested_area, device_type etc. from its creation.
        results[eid] = Entity(**ent)
    return results


@app.get("/meta", response_model=Dict[str, List[str]])  # Removed /api/ prefix
async def metadata():
    """
    Expose groupable dimensions:
    - type        (device_type)
    - area        (suggested_area)
    - capability  (defined in mapping)
    - command     (derived from capabilities)
    """
    mapping = {
        "type": "device_type",
        "area": "suggested_area",
        "capability": "capabilities",
    }
    out: Dict[str, List[str]] = {}

    for public, internal in mapping.items():
        values = set()
        for cfg in entity_id_lookup.values():
            val = cfg.get(internal)
            if isinstance(val, list):
                values.update(val)
            elif val is not None:  # Corrected from 'is not none'
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
    # Add groups to meta
    all_groups = set()
    for cfg in entity_id_lookup.values():
        grps = cfg.get("groups")  # Changed from locations
        if grps and isinstance(grps, list):
            all_groups.update(grps)
    out["groups"] = sorted(list(all_groups))  # Changed from locations to groups

    return out


@app.get("/healthz")  # Removed /api/ prefix
async def healthz():
    """Liveness probe."""
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.get("/readyz")  # Removed /api/ prefix
async def readyz():
    """
    Readiness probe: 200 once at least one frame decoded, else 503.
    """
    ready = len(state) > 0
    code = 200 if ready else 503
    return JSONResponse(
        status_code=code,
        content={"status": "ready" if ready else "pending", "entities": len(state)},
    )


@app.get("/metrics")  # Removed /api/ prefix
def metrics():
    """Prometheus metrics endpoint."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/config/device_mapping", response_class=PlainTextResponse)  # Removed /api/ prefix
async def get_device_mapping_config_content_api():
    # Serves the content of the device mapping file that the application is effectively using.
    if os.path.exists(actual_map_path_for_ui):
        try:
            with open(actual_map_path_for_ui, "r") as f:
                return PlainTextResponse(f.read())
        except Exception as e:
            logger.error(
                f"API Error: Could not read device mapping from " f"'{actual_map_path_for_ui}': {e}"
            )
            raise HTTPException(
                status_code=500, detail=f"Error reading device mapping file: {str(e)}"
            )
    else:
        logger.error(
            f"API Error: Device mapping file not found for UI display at "
            f"'{actual_map_path_for_ui}'"
        )
        raise HTTPException(status_code=404, detail="Device mapping file not found.")


# Removed CONFIG_PATH, RVC_SPEC_FILE, DEVICE_MAPPING_FILE definitions from previous version


@app.get("/config/rvc_spec_details")
async def get_rvc_spec_details():
    """Returns metadata from the rvc.json spec file."""
    # Use actual_spec_path_for_ui which is determined at startup
    if not os.path.exists(actual_spec_path_for_ui):
        logger.error(
            f"RVC spec file not found at {actual_spec_path_for_ui} " f"for spec details endpoint"
        )
        raise HTTPException(
            status_code=404, detail=f"RVC spec file not found at {actual_spec_path_for_ui}"
        )
    try:
        with open(actual_spec_path_for_ui, "r") as f:  # Use the correct path
            spec_data = json.load(f)
        return {
            "version": spec_data.get("version"),
            "spec_document": spec_data.get("spec_document"),
        }
    except json.JSONDecodeError:
        logger.error(f"Error decoding RVC spec from {actual_spec_path_for_ui}")
        raise HTTPException(status_code=500, detail="Error decoding RVC spec file.")
    except Exception as e:
        logger.error(f"Error reading RVC spec from {actual_spec_path_for_ui}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading RVC spec file: {str(e)}")


@app.get("/config/rvc_spec_metadata")
async def get_rvc_spec_metadata():
    """Returns metadata (version and spec_document URL) from the rvc.json spec file."""
    if not os.path.exists(actual_spec_path_for_ui):
        logger.error(
            f"API Error: RVC spec file not found at '{actual_spec_path_for_ui}' "
            f"for metadata endpoint"
        )
        raise HTTPException(status_code=404, detail="RVC spec file not found.")
    try:
        with open(actual_spec_path_for_ui, "r") as f:  # Corrected line
            spec_data = json.load(f)
        return {
            "version": spec_data.get("version"),
            "spec_document": spec_data.get("spec_document"),
        }
    except json.JSONDecodeError:
        logger.error(f"API Error: Could not decode RVC spec from '{actual_spec_path_for_ui}'")
        raise HTTPException(status_code=500, detail="Error decoding RVC spec file.")
    except Exception as e:
        logger.error(f"API Error: Could not read RVC spec from '{actual_spec_path_for_ui}': {e}")
        raise HTTPException(status_code=500, detail=f"Error reading RVC spec file: {str(e)}")


@app.get("/config/rvc_spec", response_class=PlainTextResponse)  # Removed /api/ prefix
async def get_rvc_spec_config_content_api():
    # Serves the content of the RVC spec file that the application is effectively using.
    if os.path.exists(actual_spec_path_for_ui):
        try:
            with open(actual_spec_path_for_ui, "r") as f:
                return PlainTextResponse(f.read())
        except Exception as e:
            logger.error(
                f"API Error: Could not read RVC spec from " f"'{actual_spec_path_for_ui}': {e}"
            )
            raise HTTPException(status_code=500, detail=f"Error reading RVC spec file: {str(e)}")
    else:
        logger.error(
            f"API Error: RVC spec file not found for UI display at " f"'{actual_spec_path_for_ui}'"
        )
        raise HTTPException(status_code=404, detail="RVC spec file not found.")


# Use imported WebSocket handlers
@app.websocket("/ws")  # Removed /api/ prefix
async def serve_websocket_endpoint(ws: WebSocket):
    await websocket_endpoint(ws)  # Call the correctly imported function


@app.websocket("/ws/logs")  # Removed /api/ prefix
async def serve_websocket_logs_endpoint(ws: WebSocket):
    await websocket_logs_endpoint(ws)  # Call the correctly imported function


async def _send_light_can_command(
    entity_id: str, target_brightness_ui: int, action_description: str  # 0-100
) -> bool:
    """
    Helper function to construct, send a CAN command for a light, and perform optimistic update.
    Returns True if the command was successfully queued, False otherwise.
    """
    if entity_id not in light_command_info:
        logger.error(
            f"Control Error: {entity_id} not found in light_command_info for "
            f"action '{action_description}'."
        )
        return False

    info = light_command_info[entity_id]
    pgn = info["dgn"]  # Reinstate pgn
    instance = info["instance"]  # Reinstate instance
    interface = info["interface"]  # This is still used below

    # Scale UI brightness (0-100) to CAN brightness level
    # (0-200, capped at 0xC8 as per RV-C for 100%)
    brightness_can_level = min(target_brightness_ui * 2, 0xC8)

    # Use the new function from can_manager.py to create the CAN message
    msg = create_light_can_message(pgn, instance, brightness_can_level)

    logger.info(
        f"CAN CMD OUT (Helper): entity_id={entity_id}, "
        f"arbitration_id=0x{msg.arbitration_id:08X}, "  # Use msg.arbitration_id
        f"data={msg.data.hex().upper()}, instance={instance}, "  # Use msg.data
        f"action='{action_description}'"
    )

    # Use the imported can_tx_queue from can_manager.py
    try:
        # msg is already created by create_light_can_message
        with CAN_TX_ENQUEUE_LATENCY.time():
            await can_tx_queue.put((msg, interface))
            CAN_TX_ENQUEUE_TOTAL.inc()
        CAN_TX_QUEUE_LENGTH.set(can_tx_queue.qsize())
        logger.info(
            f"CAN CMD Queued (Helper): '{action_description}' for {entity_id} "
            f"(CAN Lvl: {brightness_can_level}) -> {interface}"
        )

        # Optimistic State Update
        optimistic_state_str = "on" if target_brightness_ui > 0 else "off"
        optimistic_raw_val = {
            "operating_status": brightness_can_level,
            "instance": instance,  # Reinstate instance here
            "group": 0x7C,
        }
        # Ensure 'value' reflects the UI-scale brightness (0-100) for operating_status
        optimistic_value_val = {
            "operating_status": str(target_brightness_ui),
            "instance": str(instance),  # Reinstate instance here
            "group": str(0x7C),
        }
        ts = time.time()
        lookup = entity_id_lookup.get(entity_id, {})

        # Construct the complete payload for the optimistic update
        optimistic_payload_to_store = {
            "entity_id": entity_id,
            "value": optimistic_value_val,
            "raw": optimistic_raw_val,
            "state": optimistic_state_str,
            "timestamp": ts,
            "suggested_area": lookup.get(
                "suggested_area", state.get(entity_id, {}).get("suggested_area", "Unknown")
            ),
            "device_type": lookup.get(
                "device_type", state.get(entity_id, {}).get("device_type", "light")
            ),
            "capabilities": lookup.get(
                "capabilities", state.get(entity_id, {}).get("capabilities", [])
            ),
            "friendly_name": lookup.get(
                "friendly_name", state.get(entity_id, {}).get("friendly_name")
            ),
            "groups": lookup.get("groups", state.get(entity_id, {}).get("groups", [])),
        }

        # Call the centralized state update function from app_state.py
        update_entity_state_and_history(entity_id, optimistic_payload_to_store)

        # The lines for directly updating state, history, ENTITY_COUNT, HISTORY_SIZE_GAUGE
        # are now handled by update_entity_state_and_history and can be removed from here.
        # state[entity_id] = current_payload # Removed
        # ENTITY_COUNT.set(len(state)) # Removed
        # if entity_id in history: # Removed block
        # else: # Removed block

        text = json.dumps(optimistic_payload_to_store)  # Use the constructed payload for broadcast
        await broadcast_to_clients(text)
        return True
    except Exception as e:
        logger.error(
            f"Failed to enqueue or optimistically update CAN control for {entity_id} "
            f"(Action: '{action_description}'): {e}",
            exc_info=True,
        )
        return False


@app.post("/entities/{entity_id}/control", response_model=ControlEntityResponse)
async def control_entity(
    entity_id: str,
    cmd: ControlCommand = Body(
        ...,
        examples={
            "turn_on": {"summary": "Turn light on", "value": {"command": "set", "state": "on"}},
            "turn_off": {"summary": "Turn light off", "value": {"command": "set", "state": "off"}},
            "set_brightness": {
                "summary": "Set brightness to 75%",
                "value": {"command": "set", "state": "on", "brightness": 75},
            },
            "toggle": {"summary": "Toggle current state", "value": {"command": "toggle"}},
            "brightness_up": {
                "summary": "Increase brightness by 10%",
                "value": {"command": "brightness_up"},
            },
            "brightness_down": {
                "summary": "Decrease brightness by 10%",
                "value": {"command": "brightness_down"},
            },
        },
    ),
) -> ControlEntityResponse:
    device = entity_id_lookup.get(entity_id)
    if not device:
        logger.debug(f"Control command for unknown entity_id: {entity_id}")
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity_id not in light_command_info:
        logger.debug(f"Control command for non-controllable entity_id: {entity_id}")
        raise HTTPException(status_code=400, detail="Entity is not controllable")

    logger.info(
        f"HTTP CMD RX: entity_id='{entity_id}', command='{cmd.command}', "
        f"state='{cmd.state}', brightness='{cmd.brightness}'"
    )

    # info = light_command_info[entity_id]
    # pgn = info["dgn"]  # This is the PGN, e.g., 0x1FEDB for DC_DIMMER_COMMAND_2
    # instance = info["instance"] # instance was removed
    # interface = info["interface"] # interface was removed

    # --- Read Current State ---
    current_state_data = state.get(entity_id, {})
    current_on_str = current_state_data.get("state", "off")
    current_on = current_on_str.lower() == "on"
    current_raw_values = current_state_data.get("raw", {})
    current_brightness_raw = current_raw_values.get("operating_status", 0)  # Added back
    current_brightness_ui = min(int(current_brightness_raw) // 2, 100)

    # Get or initialize last known brightness for this entity
    last_brightness_ui = get_last_known_brightness(entity_id)  # Added

    logger.debug(
        f"Control for {entity_id}: current_on_str='{current_on_str}', "
        f"current_on={current_on}, current_brightness_ui={current_brightness_ui}%, "
        f"last_known_brightness_ui={last_brightness_ui}%"
    )

    # --- Determine Target State ---
    target_brightness_ui = current_brightness_ui  # Default: no change in brightness if already on
    action = "No change"

    if cmd.command == "set":
        if cmd.state not in {"on", "off"}:
            raise HTTPException(
                status_code=400, detail="State must be 'on' or 'off' for set command"
            )
        if cmd.state == "on":
            # If brightness is specified, use it.
            # Else, if light is already on, keep its current brightness.
            # Else (light is off and turning on without specific brightness),
            # restore last known brightness.
            if cmd.brightness is not None:
                target_brightness_ui = cmd.brightness
            elif not current_on:  # Turning on from off state, and no brightness specified
                target_brightness_ui = last_brightness_ui  # Restore last known brightness
            # If current_on is true and cmd.brightness is None,
            # target_brightness_ui remains current_brightness_ui (no change)
            action = f"Set ON to {target_brightness_ui}%"
        else:  # cmd.state == "off"
            # Store current brightness before turning off, if it was on
            if current_on and current_brightness_ui > 0:
                set_last_known_brightness(entity_id, current_brightness_ui)  # Changed
                logger.info(f"Stored last brightness for {entity_id}: {current_brightness_ui}%")
            target_brightness_ui = 0
            action = "Set OFF"

    elif cmd.command == "toggle":
        if current_on:
            # Store current brightness before toggling off
            if current_brightness_ui > 0:
                set_last_known_brightness(entity_id, current_brightness_ui)  # Changed
                logger.info(
                    f"Stored last brightness for {entity_id} before toggle OFF: "
                    f"{current_brightness_ui}%"
                )
            target_brightness_ui = 0
            action = "Toggle OFF"
        else:
            # When toggling ON from OFF state, restore last known brightness.
            target_brightness_ui = last_brightness_ui
            action = f"Toggle ON to {target_brightness_ui}%"

    elif cmd.command == "brightness_up":
        if not current_on and current_brightness_ui == 0:  # If light is off, start at 10%
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
    if target_brightness_ui > 0:
        set_last_known_brightness(entity_id, target_brightness_ui)  # Changed
        logger.info(
            f"Stored/updated last brightness for {entity_id} after command: "
            f"{target_brightness_ui}%"
        )

    if not await _send_light_can_command(entity_id, target_brightness_ui, action):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send CAN command for {entity_id} (Action: {action})",
        )

    return ControlEntityResponse(
        status="sent",
        entity_id=entity_id,
        command=cmd.command,
        brightness=target_brightness_ui,
        action=action,
    )


# --- Bulk Light Control Endpoints ---
async def _bulk_control_lights(
    group_filter: Optional[str],  # Changed from location_filter to group_filter
    command: str,
    state_cmd: Optional[str] = None,
    brightness_val: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Helper function to apply a command to multiple lights based on a group filter.
    Returns a list of results from individual control attempts.
    """
    results = []
    action_description_base = f"Bulk {command}"
    if state_cmd:
        action_description_base += f" {state_cmd}"
    if brightness_val is not None:
        action_description_base += f" to {brightness_val}%"
    if group_filter:
        logger.info(
            f"Processing bulk command for group: {group_filter}, command: {command}, "
            f"state: {state_cmd}, brightness: {brightness_val}"
        )
    else:
        logger.info(
            f"Processing bulk command for ALL lights, command: {command}, "
            f"state: {state_cmd}, brightness: {brightness_val}"
        )

    controlled_entity_ids = set()  # Keep track of entities already processed

    for entity_id, entity_config in entity_id_lookup.items():
        if entity_id in controlled_entity_ids:  # Skip if already processed
            continue

        # Filter by group if group_filter is provided
        if group_filter and group_filter not in entity_config.get("groups", []):
            continue

        # Ensure this entity is a light and is controllable
        if entity_id not in light_command_info or entity_config.get("device_type") != "light":
            continue

        # --- Read Current State for this light ---
        current_state_data = state.get(entity_id, {})
        current_on_str = current_state_data.get("state", "off")
        current_on = current_on_str.lower() == "on"
        current_raw_values = current_state_data.get("raw", {})
        current_brightness_raw = current_raw_values.get("operating_status", 0)
        current_brightness_ui = min(int(current_brightness_raw) // 2, 100)
        last_brightness_ui = get_last_known_brightness(entity_id)

        # --- Determine Target State for this light ---
        target_brightness_ui = current_brightness_ui
        action_suffix = ""

        if command == "set":
            if state_cmd not in {"on", "off"}:
                results.append(
                    {
                        "entity_id": entity_id,
                        "status": "error",
                        "detail": "State must be 'on' or 'off' for set command",
                    }
                )
                continue
            if state_cmd == "on":
                if brightness_val is not None:
                    target_brightness_ui = brightness_val
                elif not current_on:
                    target_brightness_ui = last_brightness_ui
                action_suffix = f"ON to {target_brightness_ui}%"
            else:  # state_cmd == "off"
                if current_on and current_brightness_ui > 0:
                    set_last_known_brightness(entity_id, current_brightness_ui)
                target_brightness_ui = 0
                action_suffix = "OFF"

        elif command == "toggle":
            if current_on:
                if current_brightness_ui > 0:
                    set_last_known_brightness(entity_id, current_brightness_ui)
                target_brightness_ui = 0
                action_suffix = "Toggle OFF"
            else:
                target_brightness_ui = last_brightness_ui
                action_suffix = f"Toggle ON to {target_brightness_ui}%"

        elif command == "brightness_up":
            if not current_on and current_brightness_ui == 0:
                target_brightness_ui = 10
            else:
                target_brightness_ui = min(current_brightness_ui + 10, 100)
            action_suffix = f"Brightness UP to {target_brightness_ui}%"

        elif command == "brightness_down":
            target_brightness_ui = max(current_brightness_ui - 10, 0)
            action_suffix = f"Brightness DOWN to {target_brightness_ui}%"
        else:
            results.append(
                {
                    "entity_id": entity_id,
                    "status": "error",
                    "detail": f"Invalid command: {command}",
                }
            )
            continue

        full_action_description = f"{action_description_base} ({action_suffix}) for {entity_id}"

        if target_brightness_ui > 0:
            set_last_known_brightness(entity_id, target_brightness_ui)

        success = await _send_light_can_command(
            entity_id, target_brightness_ui, full_action_description
        )
        results.append(
            {
                "entity_id": entity_id,
                "status": "sent" if success else "error",
                "action": full_action_description,
                "brightness": target_brightness_ui,
            }
        )
        controlled_entity_ids.add(entity_id)  # Mark as processed

    if not controlled_entity_ids:
        logger.warning(
            f"Bulk control command ({action_description_base}) did not match any lights "
            f"for group_filter: '{group_filter}'."
        )

    return results


@app.post("/lights/control", response_model=BulkLightControlResponse)
async def control_lights_bulk(
    cmd: ControlCommand = Body(...),
    group: Optional[str] = Query(None, description="Group to apply the command to"),
):
    """
    Control multiple lights based on a group or all lights if no group is specified.
    Example: Turn all 'kitchen' lights on: POST /lights/control?group=kitchen with body
    {"command": "set", "state": "on"}
    Example: Turn ALL lights off: POST /lights/control with body {"command": "set", "state": "off"}
    """
    logger.info(
        f"HTTP Bulk CMD RX: group='{group}', command='{cmd.command}', "
        f"state='{cmd.state}', brightness='{cmd.brightness}'"
    )

    results = await _bulk_control_lights(
        group_filter=group,
        command=cmd.command,
        state_cmd=cmd.state,
        brightness_val=cmd.brightness,
    )

    # Determine overall status
    if not results:  # No lights were targeted
        # Consider if this case should be a 404 or a specific message
        # For now, returning a 200 with a message indicating no lights matched.
        return BulkLightControlResponse(
            status="no_match",
            message=f"No lights found for the specified criteria (group: {group}).",
            group=group,
            command=cmd.command,
            details=[],
        )

    # Check if all individual operations were successful
    all_successful = all(r.get("status") == "sent" for r in results)
    overall_status = "success" if all_successful else "partial_error"

    # If any operation failed, it might be good to log that here or
    # ensure _bulk_control_lights does.
    if not all_successful:
        logger.warning(
            f"Partial error in bulk light control for group" f"'{group}', command '{cmd.command}'."
        )

    return BulkLightControlResponse(
        status=overall_status,
        message="Bulk command processing complete.",
        group=group,
        command=cmd.command,
        details=results,
    )


# ── Main Application Setup ───────────────────────────────────────────────────


@app.get("/queue", response_model=dict)  # Removed /api/ prefix
async def get_queue_status():
    """
    Return the current status of the CAN transmit queue.
    """
    # Use the imported can_tx_queue from can_manager.py
    return {"length": can_tx_queue.qsize(), "maxsize": can_tx_queue.maxsize or "unbounded"}


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("rvc2api shutting down...")


@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.exception_handler(ResponseValidationError)
async def validation_exception_handler(request, exc):
    return PlainTextResponse(f"Validation error: {exc}", status_code=500)


def main():
    """Runs the FastAPI application using Uvicorn."""
    # Configuration for Uvicorn can be extended here (e.g., from environment variables)
    # For example, to set host and port from environment variables with defaults:
    host = os.getenv("RVC2API_HOST", "0.0.0.0")
    port = int(os.getenv("RVC2API_PORT", "8000"))
    log_level = os.getenv("RVC2API_LOG_LEVEL", "info").lower()

    logger.info(f"Starting Uvicorn server on {host}:{port} with log level '{log_level}'")
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    # This allows running the app directly with `python app.py` for development
    # The script entry point `rvc2api-daemon` will call the `main()` function.
    main()
