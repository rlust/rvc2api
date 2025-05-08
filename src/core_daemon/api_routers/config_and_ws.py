import json
import logging
import os
from typing import Any, Dict  # Removed List, Optional, Union

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect  # Removed Query
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)  # Added Response, Removed HTMLResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from core_daemon import app_state  # For readyz and unmapped_entries
from core_daemon.config import ACTUAL_MAP_PATH, ACTUAL_SPEC_PATH, get_actual_paths
from core_daemon.websocket import (
    ConnectionManager,
    WebSocketLogHandler,
    websocket_endpoint,
    websocket_logs_endpoint,
)

logger = logging.getLogger(__name__)

api_router_config_ws = APIRouter()

# WebSocket connection manager
manager = ConnectionManager()

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
    await websocket_endpoint(ws)


@api_router_config_ws.websocket("/ws/logs")
async def serve_websocket_logs_endpoint(ws: WebSocket):
    await websocket_logs_endpoint(ws)


# ── WebSocket Endpoint for Logs ──────────────────────────────────────────────
@api_router_config_ws.websocket("/ws/logs")
async def websocket_log_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # Add the WebSocket to the log handler's list of active WebSockets
    # This assumes WebSocketLogHandler.add_client and .remove_client are implemented
    # to manage individual WebSocket connections for log streaming.
    root_logger = logging.getLogger()
    ws_handler = None
    for handler in root_logger.handlers:
        if isinstance(handler, WebSocketLogHandler):
            ws_handler = handler
            break

    if ws_handler:
        ws_handler.add_client(websocket)
    else:
        logger.error("WebSocketLogHandler not found in root logger handlers.")

    try:
        while True:
            # Keep the connection alive, logs are pushed by the handler
            await websocket.receive_text()  # Or use receive_bytes if that's expected
    except WebSocketDisconnect:
        logger.info("WebSocket for logs disconnected.")
    finally:
        manager.disconnect(websocket)
        if ws_handler:
            ws_handler.remove_client(websocket)


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


# ── Unmapped DGNs/PGNs Endpoint ──────────────────────────────────────────────
@api_router_config_ws.get("/unmapped")
async def get_unmapped_entries_api() -> Dict[str, Any]:
    # Access unmapped_entries directly from app_state
    return app_state.unmapped_entries
