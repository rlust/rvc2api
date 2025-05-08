#!/usr/bin/env python3
import asyncio
import functools  # Added for functools.partial
import json
import logging
import os

# import re # Unused import
import time

# from typing import Any, Dict, List, Optional # Unused import (List was unused)
from typing import Any, Dict, Optional  # Keep Any, Dict, Optional for _process_can_message

import can
import uvicorn
from fastapi import FastAPI, Request  # Response, # Unused import
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import HTMLResponse, PlainTextResponse  # Removed JSONResponse (unused)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Import application state variables and initialization function
from core_daemon import app_state  # Import the module itself

# App state used by _process_can_message, moved to top
from core_daemon.app_state import unmapped_entries  # Keep for _process_can_message
from core_daemon.app_state import update_entity_state_and_history  # Keep for _process_can_message
from core_daemon.app_state import initialize_history_deques, preseed_light_states

# Import CAN components from can_manager
from core_daemon.can_manager import initialize_can_listeners, initialize_can_writer_task
from core_daemon.config import (
    configure_logger,
    get_actual_paths,
    get_canbus_config,
    get_fastapi_config,
    get_static_paths,
)

# Metrics that are specific to _process_can_message or global
from core_daemon.metrics import HTTP_LATENCY  # Used by middleware
from core_daemon.metrics import HTTP_REQUESTS  # Used by middleware
from core_daemon.metrics import (
    DECODE_ERRORS,
    DGN_TYPE_GAUGE,
    FRAME_COUNTER,
    FRAME_LATENCY,
    GENERATOR_COMMAND_COUNTER,
    GENERATOR_DEMAND_COMMAND_COUNTER,
    GENERATOR_STATUS_1_COUNTER,
    GENERATOR_STATUS_2_COUNTER,
    INST_USAGE_COUNTER,
    LOOKUP_MISSES,
    PGN_USAGE_COUNTER,
    SUCCESSFUL_DECODES,
)

# Models used by _process_can_message
from core_daemon.models import SuggestedMapping, UnmappedEntryModel
from core_daemon.websocket import broadcast_to_clients  # Moved to top for _process_can_message
from core_daemon.websocket import WebSocketLogHandler
from rvc_decoder import decode_payload, load_config_data

# Import the new routers
from .api_routers.can import api_router_can
from .api_routers.config_and_ws import api_router_config_ws
from .api_routers.entities import api_router_entities

# ── Logging ──────────────────────────────────────────────────────────────────
logger = configure_logger()

logger.info("rvc2api starting up...")

# ── Determine actual config paths for core logic and UI display ────────────────
actual_spec_path_for_ui, actual_map_path_for_ui = get_actual_paths()

# ── Load spec & mappings for core logic ──────────────────────────────────────
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
    _light_entity_ids,  # Use temporary names to avoid conflict if needed
    _entity_id_lookup,  # or ensure they are not needed here if already in app_state
    _light_command_info,
    pgn_hex_to_name_map,
) = load_config_data(
    rvc_spec_path_override=os.getenv("CAN_SPEC_PATH"),
    device_mapping_path_override=os.getenv("CAN_MAP_PATH"),
)

# Populate the global config variables in app_state module
app_state.entity_id_lookup = _entity_id_lookup
app_state.light_entity_ids = _light_entity_ids
app_state.light_command_info = _light_command_info
# Optionally, populate others if they are also made global in app_state
# app_state.decoder_map = decoder_map
# app_state.raw_device_mapping = raw_device_mapping
# app_state.device_lookup = device_lookup
# app_state.status_lookup = status_lookup
# app_state.pgn_hex_to_name_map = pgn_hex_to_name_map

# Initialize history deques after entity_id_lookup is populated in app_state
initialize_history_deques(app_state.entity_id_lookup)

# Call the new pre-seeding function from app_state.py
preseed_light_states(
    light_entity_ids=app_state.light_entity_ids,
    light_command_info=app_state.light_command_info,
    decoder_map_values=list(decoder_map.values()),  # decoder_map is local to main.py
    entity_id_lookup=app_state.entity_id_lookup,
    decode_payload_func=decode_payload,
)

# ── FastAPI setup ──────────────────────────────────────────────────────────
fastapi_config = get_fastapi_config()
API_TITLE = fastapi_config["title"]
API_SERVER_DESCRIPTION = fastapi_config["server_description"]
API_ROOT_PATH = fastapi_config["root_path"]

logger.info(f"API Title: {API_TITLE}")
logger.info(f"API Server Description: {API_SERVER_DESCRIPTION}")
logger.info(f"API Root Path: {API_ROOT_PATH}")

app = FastAPI(
    title=API_TITLE,
    servers=[{"url": "/", "description": API_SERVER_DESCRIPTION}],
    root_path=API_ROOT_PATH,
)

static_paths = get_static_paths()
web_ui_dir = static_paths["web_ui_dir"]
static_dir = static_paths["static_dir"]
templates_dir = static_paths["templates_dir"]

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)


# @app.on_event("startup")
# async def ensure_static_dir_exists():
#     static_dir_for_mount = os.path.join(web_ui_dir, "static")
#     os.makedirs(static_dir_for_mount, exist_ok=True)
#     logger.info(f"Ensured static directory for mount exists: {static_dir_for_mount}")


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


@app.on_event("startup")
async def start_can_writer():
    initialize_can_writer_task()


@app.on_event("startup")
async def setup_websocket_logging():
    try:
        main_loop = asyncio.get_running_loop()
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
            return

        decoded, raw = decode_payload(entry, msg.data)
        decoded_payload_for_unmapped = decoded
        SUCCESSFUL_DECODES.inc()

    except Exception as e:
        logger.error(
            f"Decode error for PGN 0x{msg.arbitration_id:X} on {iface_name}: {e}",
            exc_info=True,
        )
        DECODE_ERRORS.inc()
        return
    finally:
        FRAME_LATENCY.observe(time.perf_counter() - start_time)

    dgn = entry.get("dgn_hex")
    inst = raw.get("instance")

    if not dgn or inst is None:
        LOOKUP_MISSES.inc()
        logger.debug(
            f"DGN or instance missing in decoded payload for PGN "
            f"0x{msg.arbitration_id:X} (Spec DGN: {entry.get('dgn_hex')}). "
            f"DGN from payload: {dgn}, Instance from payload: {inst}"
        )
        return

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
        return

    ts = time.time()
    raw_brightness = raw.get("operating_status", 0)
    state_str = "on" if raw_brightness > 0 else "off"

    for device in matching_devices:
        eid = device["entity_id"]
        lookup_data = app_state.entity_id_lookup.get(eid, {})
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
        pgn_val = msg.arbitration_id & 0x3FFFF
        PGN_USAGE_COUNTER.labels(pgn=f"{pgn_val:X}").inc()
        INST_USAGE_COUNTER.labels(dgn=dgn.upper(), instance=str(inst)).inc()
        device_type = device.get("device_type", "unknown")
        DGN_TYPE_GAUGE.labels(device_type=device_type).set(1)

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

    message_handler_with_loop = functools.partial(_process_can_message, loop=loop)

    initialize_can_listeners(
        interfaces=interfaces,
        bustype=bustype,
        bitrate=bitrate,
        message_handler_callback=message_handler_with_loop,
        logger_instance=logger,
    )


# ── Main Application Setup ───────────────────────────────────────────────────
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("rvc2api shutting down...")


@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


app.include_router(api_router_can, prefix="/api")
app.include_router(api_router_config_ws, prefix="/api")
app.include_router(api_router_entities, prefix="/api")


@app.exception_handler(ResponseValidationError)
async def validation_exception_handler(request, exc):
    return PlainTextResponse(f"Validation error: {exc}", status_code=500)


def main():
    host = os.getenv("RVC2API_HOST", "0.0.0.0")
    port = int(os.getenv("RVC2API_PORT", "8000"))
    log_level = os.getenv("RVC2API_LOG_LEVEL", "info").lower()

    logger.info(f"Starting Uvicorn server on {host}:{port} with log level '{log_level}'")
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
