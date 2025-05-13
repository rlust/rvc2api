#!/usr/bin/env python3
"""
Main entry point and central orchestrator for the rvc2api daemon.

This script initializes and runs the FastAPI application that bridges RV-C (Recreational
Vehicle Controller Area Network) messages to a modern web API and WebSocket interface.

Key responsibilities include:
- Configuring application-wide logging.
- Loading RV-C specification and device mapping configurations.
- Initializing and managing shared application state (see app_state.py).
- Setting up and starting CAN bus listeners to receive RV-C messages (see can_manager.py).
- Starting a CAN bus writer task to send commands to the RV-C bus.
- Processing incoming CAN messages, decoding them, and updating entity states
(see can_processing.py).
- Initializing the FastAPI application, including:
    - Mounting static file directories and template engines for the web UI.
    - Setting up Prometheus metrics middleware.
    - Registering API routers for various functionalities
    (entities, CAN control, config, WebSockets).
    - Defining startup and shutdown event handlers.
- Providing a command-line interface to start the Uvicorn server.
"""
import asyncio
import functools
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Import application state variables and initialization function
from core_daemon import app_state  # Import the module itself
from core_daemon.app_state import initialize_app_from_config

# Import CAN components from can_manager
from core_daemon.can_manager import initialize_can_listeners, initialize_can_writer_task

# Import the new CAN processing function
from core_daemon.can_processing import process_can_message
from core_daemon.config import (
    configure_logger,
    get_actual_paths,
    get_canbus_config,
    get_fastapi_config,
    get_static_paths,
)

# Import the feature manager
from core_daemon.feature_manager import shutdown_all as feature_shutdown_all
from core_daemon.feature_manager import startup_all as feature_startup_all

# Import the middleware
from core_daemon.middleware import prometheus_http_middleware
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
# Load all configuration data into a tuple
config_data_tuple = load_config_data(
    rvc_spec_path_override=os.getenv("CAN_SPEC_PATH"),
    device_mapping_path_override=os.getenv("CAN_MAP_PATH"),
)

# Initialize application state using the loaded configuration data
# and the decode_payload function from rvc_decoder
initialize_app_from_config(config_data_tuple, decode_payload)


def create_app():
    # ── FastAPI setup ──────────────────────────────────────────────────────────
    fastapi_config = get_fastapi_config()
    API_TITLE = fastapi_config["title"]
    API_SERVER_DESCRIPTION = fastapi_config["server_description"]
    API_ROOT_PATH = fastapi_config["root_path"]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # --- Startup ---
        initialize_can_writer_task()
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

        loop = asyncio.get_running_loop()
        canbus_config = get_canbus_config()
        interfaces = canbus_config["channels"]
        bustype = canbus_config["bustype"]
        bitrate = canbus_config["bitrate"]
        message_handler_with_args = functools.partial(
            process_can_message,
            loop=loop,
            decoder_map=app_state.decoder_map,
            device_lookup=app_state.device_lookup,
            status_lookup=app_state.status_lookup,
            pgn_hex_to_name_map=app_state.pgn_hex_to_name_map,
            raw_device_mapping=app_state.raw_device_mapping,
        )
        initialize_can_listeners(
            interfaces=interfaces,
            bustype=bustype,
            bitrate=bitrate,
            message_handler_callback=message_handler_with_args,
            logger_instance=logger,
        )
        await feature_startup_all()
        yield
        # --- Shutdown ---
        await feature_shutdown_all()
        logger.info("rvc2api shutting down...")

    app = FastAPI(
        title=API_TITLE,
        servers=[{"url": "/", "description": API_SERVER_DESCRIPTION}],
        root_path=API_ROOT_PATH,
        lifespan=lifespan,
    )

    # ── Static files and templates ─────────────────────────────────────────────
    static_paths = get_static_paths()
    static_dir = static_paths["static_dir"]
    templates_dir = static_paths["templates_dir"]

    if static_dir and os.path.isdir(static_dir):
        app.mount(
            "/static",
            StaticFiles(
                directory=static_dir,
                follow_symlink=True,
            ),
            name="static",
        )
        logger.info(f"Successfully mounted /static to directory: {static_dir}")
    else:
        logger.error(
            f"Static directory ('{static_dir}') is invalid or not found;"
            f"static files will not be served."
        )

    if templates_dir and os.path.isdir(templates_dir):
        templates = Jinja2Templates(directory=templates_dir)
        logger.info(f"Successfully initialized Jinja2Templates with directory: {templates_dir}")
    else:
        logger.error(
            f"Templates directory ('{templates_dir}') is invalid or not found;"
            f"templates will not be loaded."
        )
        templates = None

    # ── Middleware ─────────────────────────────────────────────────────────────
    @app.middleware("http")
    async def prometheus_middleware_handler(request, call_next):
        """Prometheus metrics middleware for HTTP requests."""
        return await prometheus_http_middleware(request, call_next)

    # ── Exception Handlers ─────────────────────────────────────────────────────
    @app.exception_handler(ResponseValidationError)
    async def validation_exception_handler(request, exc):
        """Handles response validation errors with a plain text message."""
        return PlainTextResponse(f"Validation error: {exc}", status_code=500)

    # ── Top-level UI Route ─────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def serve_home(request: Request):
        """Serves the main UI HTML page."""
        return templates.TemplateResponse("index.html", {"request": request})

    # ── API Routers ────────────────────────────────────────────────────────────
    app.include_router(api_router_can, prefix="/api")
    app.include_router(api_router_config_ws, prefix="/api")
    app.include_router(api_router_entities, prefix="/api")

    return app


app = create_app()


# ── Entrypoint ─────────────────────────────────────────────────────────────
def main():
    """
    Main function to run the Uvicorn server for the rvc2api application.

    Retrieves host, port, and log level from environment variables or defaults,
    then starts the Uvicorn server.
    """
    host = os.getenv("RVC2API_HOST", "0.0.0.0")
    port = int(os.getenv("RVC2API_PORT", "8000"))
    log_level = os.getenv("RVC2API_LOG_LEVEL", "info").lower()

    logger.info(f"Starting Uvicorn server on {host}:{port} with log level '{log_level}'")
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
