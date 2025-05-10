"""
Manages API routes for configuration and WebSocket interactions.

This module provides FastAPI endpoints for:
- Retrieving the current application configuration.
- Managing WebSocket connections for real-time updates (e.g., CAN messages, logs).
- Providing server and application status.
- Streaming application logs to WebSocket clients.
"""

import json
import logging
import os
import time  # Added for uptime

from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from core_daemon import app_state
from core_daemon._version import VERSION  # Import VERSION
from core_daemon.config import ACTUAL_MAP_PATH, ACTUAL_SPEC_PATH, get_actual_paths
from core_daemon.websocket import websocket_endpoint, websocket_logs_endpoint

logger = logging.getLogger(__name__)

api_router_config_ws = APIRouter()  # Router for configuration, status, and WebSocket endpoints

# Get actual paths once for this module
actual_spec_path_for_ui, actual_map_path_for_ui = get_actual_paths()

# Store startup time
SERVER_START_TIME = time.time()


@api_router_config_ws.get("/healthz")
async def healthz():
    """Liveness probe."""
    return JSONResponse(status_code=200, content={"status": "ok"})


@api_router_config_ws.get("/readyz")
async def readyz():
    """
    Readiness probe: 200 once at least one frame decoded, else 503.
    """
    ready = len(app_state.state) > 0
    code = 200 if ready else 503
    return JSONResponse(
        status_code=code,
        content={"status": "ready" if ready else "pending", "entities": len(app_state.state)},
    )


@api_router_config_ws.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@api_router_config_ws.get("/config/device_mapping", response_class=PlainTextResponse)
async def get_device_mapping_config_content_api():
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


@api_router_config_ws.get("/config/rvc_spec_metadata")
async def get_rvc_spec_metadata():
    """Returns metadata (version and spec_document URL) from the rvc.json spec file."""
    if not os.path.exists(actual_spec_path_for_ui):
        logger.error(
            f"API Error: RVC spec file not found at '{actual_spec_path_for_ui}' "
            f"for metadata endpoint"
        )
        raise HTTPException(status_code=404, detail="RVC spec file not found.")
    try:
        with open(actual_spec_path_for_ui, "r") as f:
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


@api_router_config_ws.get("/config/rvc_spec", response_class=PlainTextResponse)
async def get_rvc_spec_config_content_api():
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


# --- New Status Endpoints ---
@api_router_config_ws.get("/status/server")
async def get_server_status():
    """Returns basic server status information."""
    uptime_seconds = time.time() - SERVER_START_TIME
    return {
        "status": "ok",
        "version": VERSION,
        "server_start_time_unix": SERVER_START_TIME,
        "uptime_seconds": uptime_seconds,
        "message": "rvc2api server is running.",
    }


@api_router_config_ws.get("/status/application")
async def get_application_status():
    """Returns application-specific status information."""
    # Check if config files were loaded (using the global ACTUAL_SPEC_PATH and ACTUAL_MAP_PATH)
    spec_loaded = ACTUAL_SPEC_PATH is not None and os.path.exists(ACTUAL_SPEC_PATH)
    map_loaded = ACTUAL_MAP_PATH is not None and os.path.exists(ACTUAL_MAP_PATH)

    # Basic check for CAN listeners (more detailed status could be added)
    # This is a placeholder; actual CAN listener status might need more complex state tracking.
    can_listeners_active = (
        len(app_state.state) > 0
    )  # Simple proxy: if entities exist, listeners likely ran

    return {
        "status": "ok",
        "rvc_spec_file_loaded": spec_loaded,
        "rvc_spec_file_path": ACTUAL_SPEC_PATH if spec_loaded else None,
        "device_mapping_file_loaded": map_loaded,
        "device_mapping_file_path": ACTUAL_MAP_PATH if map_loaded else None,
        "known_entity_count": len(app_state.entity_id_lookup),
        "active_entity_state_count": len(app_state.state),
        "unmapped_entry_count": len(app_state.unmapped_entries),
        "unknown_pgn_count": len(app_state.unknown_pgns),
        "can_listeners_status": "likely_active" if can_listeners_active else "unknown_or_inactive",
        "websocket_clients": {
            "data_clients": len(
                app_state.clients
            ),  # Assuming 'clients' is accessible or moved to app_state
            "log_clients": len(
                app_state.log_ws_clients
            ),  # Assuming 'log_ws_clients' is accessible or moved to app_state
        },
    }


# --- End New Status Endpoints ---


@api_router_config_ws.websocket("/ws")
async def serve_websocket_endpoint(ws: WebSocket):
    """Handles WebSocket connections for general data streaming."""
    await websocket_endpoint(ws)


@api_router_config_ws.websocket("/ws/logs")
async def serve_websocket_logs_endpoint(ws: WebSocket):
    print("LOG WS HANDLER CALLED")  # Debug: confirm handler is hit
    await websocket_logs_endpoint(ws)


# ── Configuration File Endpoints ───────────────────────────────────────────
@api_router_config_ws.get("/config/spec", response_class=PlainTextResponse)
async def get_rvc_spec_file_contents():
    # ACTUAL_SPEC_PATH is now imported from config.py
    if ACTUAL_SPEC_PATH and os.path.exists(ACTUAL_SPEC_PATH):
        return FileResponse(ACTUAL_SPEC_PATH, media_type="text/plain")
    raise HTTPException(status_code=404, detail="RVC Spec file not found.")


@api_router_config_ws.get("/config/mapping", response_class=PlainTextResponse)
async def get_device_mapping_file_contents():
    print("ACTUAL_MAP_PATH:", ACTUAL_MAP_PATH)
    print("Exists:", os.path.exists(ACTUAL_MAP_PATH) if ACTUAL_MAP_PATH else None)
    # Try ACTUAL_MAP_PATH first
    if ACTUAL_MAP_PATH and os.path.exists(ACTUAL_MAP_PATH):
        return FileResponse(ACTUAL_MAP_PATH, media_type="text/plain")

    # Fallback: try the bundled default from rvc_decoder.decode._default_paths
    try:
        from rvc_decoder.decode import _default_paths

        _spec_path, default_mapping_path = _default_paths()
        if os.path.exists(default_mapping_path):
            return FileResponse(default_mapping_path, media_type="text/plain")
    except Exception as e:
        logger.error(f"Error loading fallback device mapping: {e}")

    raise HTTPException(status_code=404, detail="Device mapping file not found.")
