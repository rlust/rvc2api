import importlib.resources  # Added for robust path finding
import logging
import os

import coloredlogs

# Removed WebSocketLogHandler import as it's handled in main.py

# ── Logging Configuration ──────────────────────────────────────────────────
# This logger is for messages originating from the config.py module itself.
module_logger = logging.getLogger(__name__)


# Refactor configure_logger to properly handle logging levels and handlers
def configure_logger():
    root_logger = logging.getLogger()  # Get the root logger
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Attempt to get the integer value for the log level string
    log_level_int = getattr(logging, log_level_str, None)
    if not isinstance(log_level_int, int):
        module_logger.warning(f"Invalid LOG_LEVEL '{log_level_str}'. Defaulting to INFO.")
        log_level_int = logging.INFO

    log_format = "%(asctime)s %(name)s[%(process)d] %(levelname)s %(message)s"

    # Set the root logger's level to capture all messages from DEBUG upwards.
    # Handlers will then filter based on their own configured levels.
    root_logger.setLevel(logging.DEBUG)

    # Remove any existing handlers from the root logger to prevent duplication.
    # This is important if this function could be called multiple times or if other
    # libraries might have added handlers to the root logger.
    for handler in list(root_logger.handlers):  # Iterate over a copy for safe removal
        root_logger.removeHandler(handler)

    # Configure coloredlogs. This will add its own StreamHandler to the root logger.
    # `reconfigure=True` (default in recent versions) would also attempt to clear
    # handlers from the logger it's installed on, but explicit clearing above is safer.
    coloredlogs.install(
        level=log_level_int,  # Use the integer log level
        fmt=log_format,
        logger=root_logger,  # Install on the root logger
        reconfigure=True,  # Ensure it takes full control of the specified logger's console output
    )

    # The WebSocketLogHandler is added to the root logger in main.py's setup_websocket_logging.
    # At this point, the root_logger should have one handler from coloredlogs for console output.
    # Later, WebSocketLogHandler will be added for WebSocket output.

    return root_logger  # Return the configured root logger


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
            module_logger.warning(  # Changed from logger to module_logger
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
            module_logger.warning(  # Changed from logger to module_logger
                f"Override Device Mapping Path '{mapping_override_env}' is missing "
                f"or unreadable. Core logic will attempt to use bundled default: "
                f"'{_decoder_default_map_path}'"
            )

    module_logger.info(
        f"UI will attempt to display RVC spec from: {actual_spec_path_for_ui}"
    )  # Changed from logger to module_logger
    module_logger.info(
        f"UI will attempt to display device mapping from: {actual_map_path_for_ui}"
    )  # Changed from logger to module_logger

    return actual_spec_path_for_ui, actual_map_path_for_ui


# ── FastAPI Configuration ──────────────────────────────────────────────────
def get_fastapi_config():
    return {
        "title": os.getenv("RVC2API_TITLE", "rvc2api"),
        "server_description": os.getenv("RVC2API_SERVER_DESCRIPTION", "RV-C to API Bridge"),
        "root_path": os.getenv("RVC2API_ROOT_PATH", "/"),  # Changed default from "/api" to "/"
    }


# ── Static File and Template Paths ─────────────────────────────────────────
def get_static_paths():
    try:
        static_pkg_path = importlib.resources.files("core_daemon.web_ui.static")
        templates_pkg_path = importlib.resources.files("core_daemon.web_ui.templates")
        # web_ui_pkg_path = importlib.resources.files('core_daemon.web_ui')

        static_dir = str(static_pkg_path)
        templates_dir = str(templates_pkg_path)
        # web_ui_dir needs to be the parent of static_dir and templates_dir
        # Assuming static_dir is .../core_daemon/web_ui/static
        web_ui_dir = os.path.dirname(static_dir)

        module_logger.info(f"Located static_dir via importlib.resources: {static_dir}")
        module_logger.info(f"Located templates_dir via importlib.resources: {templates_dir}")
        module_logger.info(f"Determined web_ui_dir via importlib.resources: {web_ui_dir}")

    except (ImportError, ModuleNotFoundError) as e:
        module_logger.error(f"Could not load static/template paths via importlib.resources: {e}")
        module_logger.warning("Falling back to __file__ based paths for static/templates.")
        # Fallback to the old method if importlib.resources fails
        base_dir = os.path.dirname(os.path.abspath(__file__))  # Ensure absolute path
        web_ui_dir = os.path.join(base_dir, "web_ui")
        static_dir = os.path.join(web_ui_dir, "static")
        templates_dir = os.path.join(web_ui_dir, "templates")
        module_logger.info(f"Determined static_dir via fallback: {static_dir}")
        module_logger.info(f"Determined templates_dir via fallback: {templates_dir}")
        module_logger.info(f"Determined web_ui_dir via fallback: {web_ui_dir}")

    return {
        "web_ui_dir": web_ui_dir,
        "static_dir": static_dir,
        "templates_dir": templates_dir,
    }


# ── CAN Bus Configuration ─────────────────────────────────────────────────
def get_canbus_config():
    return {
        "channels": os.getenv("CAN_CHANNELS", "can0,can1").split(","),
        "bustype": os.getenv("CAN_BUSTYPE", "socketcan"),
        "bitrate": int(os.getenv("CAN_BITRATE", "500000")),
    }
