import asyncio
import logging
import os

import coloredlogs

from core_daemon.models import WebSocketLogHandler

# ── Logging Configuration ──────────────────────────────────────────────────
logger = logging.getLogger(__name__)


# Refactor configure_logger to properly handle logging levels and handlers
def configure_logger():
    logger = logging.getLogger()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = "%(asctime)s %(name)s[%(process)d] %(levelname)s %(message)s"

    # Set up the root logger
    logging.basicConfig(level=logging.DEBUG, format=log_format)
    logger.setLevel(logging.DEBUG)  # Root logger captures all logs

    # System-level handler for journalctl
    system_handler = logging.StreamHandler()
    system_handler.setLevel(getattr(logging, log_level, logging.INFO))
    system_handler.setFormatter(logging.Formatter(log_format))

    # Add a filter to restrict logs to INFO and above for system-level logs
    class InfoAndAboveFilter(logging.Filter):
        def filter(self, record):
            return record.levelno >= logging.INFO

    system_handler.addFilter(InfoAndAboveFilter())
    logger.addHandler(system_handler)

    # WebSocket log handler for Web UI
    try:
        main_loop = asyncio.get_running_loop()
        log_ws_handler = WebSocketLogHandler(loop=main_loop)
        log_ws_handler.setLevel(logging.DEBUG)  # Always capture DEBUG logs
        log_ws_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(log_ws_handler)
    except Exception as e:
        logger.error(f"Failed to setup WebSocket logging: {e}", exc_info=True)

    # Enhance logging with coloredlogs for console output
    coloredlogs.install(
        level=log_level,
        fmt=log_format,
        logger=logger,
    )

    return logger


# ── Determine actual config paths for core logic and UI display ────────────────
def get_actual_paths():
    spec_override_env = os.getenv("CAN_SPEC_PATH")
    mapping_override_env = os.getenv("CAN_MAP_PATH")

    from rvc_decoder.decode import _default_paths

    _decoder_default_spec_path, _decoder_default_map_path = _default_paths()

    # Determine actual spec path that will be used by load_config_data and for UI
    actual_spec_path_for_ui = _decoder_default_spec_path
    if spec_override_env:
        if os.path.exists(spec_override_env) and os.access(spec_override_env, os.R_OK):
            actual_spec_path_for_ui = spec_override_env
        else:
            logger.warning(
                f"Override RVC Spec Path '{spec_override_env}' is missing or "
                f"unreadable. Core logic will attempt to use bundled default: "
                f"'{_decoder_default_spec_path}'"
            )

    # Determine actual mapping path that will be used by load_config_data and for UI
    actual_map_path_for_ui = _decoder_default_map_path
    if mapping_override_env:
        if os.path.exists(mapping_override_env) and os.access(mapping_override_env, os.R_OK):
            actual_map_path_for_ui = mapping_override_env
        else:
            logger.warning(
                f"Override Device Mapping Path '{mapping_override_env}' is missing "
                f"or unreadable. Core logic will attempt to use bundled default: "
                f"'{_decoder_default_map_path}'"
            )

    logger.info(f"UI will attempt to display RVC spec from: {actual_spec_path_for_ui}")
    logger.info(f"UI will attempt to display device mapping from: {actual_map_path_for_ui}")

    return actual_spec_path_for_ui, actual_map_path_for_ui


# ── FastAPI Configuration ──────────────────────────────────────────────────
def get_fastapi_config():
    return {
        "title": os.getenv("RVC2API_TITLE", "rvc2api"),
        "server_description": os.getenv("RVC2API_SERVER_DESCRIPTION", "RV-C to API Bridge"),
        "root_path": os.getenv("RVC2API_ROOT_PATH", "/api"),
    }


# ── Static File and Template Paths ─────────────────────────────────────────
def get_static_paths():
    base_dir = os.path.dirname(__file__)
    return {
        "web_ui_dir": os.path.join(base_dir, "web_ui"),
        "static_dir": os.path.join(base_dir, "web_ui", "static"),
        "templates_dir": os.path.join(base_dir, "web_ui", "templates"),
    }


# ── CAN Bus Configuration ─────────────────────────────────────────────────
def get_canbus_config():
    return {
        "channels": os.getenv("CAN_CHANNELS", "can0,can1").split(","),
        "bustype": os.getenv("CAN_BUSTYPE", "socketcan"),
        "bitrate": int(os.getenv("CAN_BITRATE", "500000")),
    }
