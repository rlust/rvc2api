"""
Defines FastAPI APIRouter for application configuration, status, and WebSocket endpoints.

This module groups routes for:
- Health checks (`/healthz`, `/readyz`).
- Prometheus metrics (`/metrics`).
- Accessing RVC specification and device mapping configuration files.
- Establishing WebSocket connections for data and log streaming.
"""

import json
import logging
import os

from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from core_daemon import app_state
from core_daemon.config import ACTUAL_MAP_PATH, ACTUAL_SPEC_PATH, get_actual_paths
from core_daemon.websocket import websocket_endpoint, websocket_logs_endpoint

logger = logging.getLogger(__name__)

api_router_config_ws = APIRouter()  # Router for configuration, status, and WebSocket endpoints

# Get actual paths once for this module
actual_spec_path_for_ui, actual_map_path_for_ui = get_actual_paths()


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


@api_router_config_ws.get("/config/rvc_spec_details")
async def get_rvc_spec_details():
    """Returns metadata from the rvc.json spec file."""
    if not os.path.exists(actual_spec_path_for_ui):
        logger.error(
            f"RVC spec file not found at {actual_spec_path_for_ui} " f"for spec details endpoint"
        )
        raise HTTPException(
            status_code=404, detail=f"RVC spec file not found at {actual_spec_path_for_ui}"
        )
    try:
        with open(actual_spec_path_for_ui, "r") as f:
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


@api_router_config_ws.websocket("/ws")
async def serve_websocket_endpoint(ws: WebSocket):
    """Handles WebSocket connections for general data streaming."""
    await websocket_endpoint(ws)


@api_router_config_ws.websocket("/ws/logs")
async def serve_websocket_logs_endpoint(ws: WebSocket):
    """Handles WebSocket connections for streaming application logs."""
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
    # ACTUAL_MAP_PATH is now imported from config.py
    if ACTUAL_MAP_PATH and os.path.exists(ACTUAL_MAP_PATH):
        return FileResponse(ACTUAL_MAP_PATH, media_type="text/plain")
    raise HTTPException(status_code=404, detail="Device mapping file not found.")
