"""
Handles application configuration for the rvc2api daemon.

This module is responsible for:
- Configuring logging for the application.
- Determining and providing paths to essential configuration files (RVC spec, device mapping)
  considering environment overrides and bundled defaults.
- Providing FastAPI application settings (title, description, root_path).
- Resolving paths to static files and Jinja2 templates for the web UI,
  using importlib.resources with a fallback to __file__-based resolution.
- Providing CAN bus configuration (channels, bustype, bitrate) from environment variables.
"""

import importlib.resources  # Added for robust path finding
import logging
import os

import coloredlogs

# Removed WebSocketLogHandler import as it's handled in main.py

# ── Logging Configuration ──────────────────────────────────────────────────
# This logger is for messages originating from the config.py module itself.
module_logger = logging.getLogger(__name__)

# Module-level globals to store determined paths to configuration files.
# These are populated by get_actual_paths() after considering environment
# variables and bundled defaults.
ACTUAL_SPEC_PATH: str | None = None  # Stores the resolved path to the RVC specification file.
ACTUAL_MAP_PATH: str | None = None  # Stores the resolved path to the device mapping file.


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
    """
    Determines and returns the actual paths to the RVC specification and device mapping files.

    It considers environment variables (CAN_SPEC_PATH, CAN_MAP_PATH) for overrides.
    If overrides are not present, invalid, or unreadable, it falls back to
    default paths, typically bundled with the rvc_decoder package.
    The determined paths are stored in module-level globals ACTUAL_SPEC_PATH
    and ACTUAL_MAP_PATH to avoid re-computation.

    Returns:
        tuple[str, str]: A tuple containing the actual path to the RVC specification file
                         and the actual path to the device mapping file.
    """
    global ACTUAL_SPEC_PATH, ACTUAL_MAP_PATH  # Indicate assignment to module globals

    # If already determined, return stored values
    if ACTUAL_SPEC_PATH is not None and ACTUAL_MAP_PATH is not None:
        # module_logger.info("Returning already determined actual paths.") # Optional debug
        return ACTUAL_SPEC_PATH, ACTUAL_MAP_PATH

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

    # Store them in the global variables
    ACTUAL_SPEC_PATH = actual_spec_path_for_ui
    ACTUAL_MAP_PATH = actual_map_path_for_ui

    module_logger.info(
        f"UI will attempt to display RVC spec from: {ACTUAL_SPEC_PATH}"
    )  # Changed from logger to module_logger
    module_logger.info(
        f"UI will attempt to display device mapping from: {ACTUAL_MAP_PATH}"
    )  # Changed from logger to module_logger

    return ACTUAL_SPEC_PATH, ACTUAL_MAP_PATH


# ── FastAPI Configuration ──────────────────────────────────────────────────
def get_fastapi_config():
    """
    Retrieves FastAPI application settings from environment variables.

    Returns:
        dict: A dictionary containing title, server_description, and root_path
              for the FastAPI application.
    """
    return {
        "title": os.getenv("RVC2API_TITLE", "rvc2api"),
        "server_description": os.getenv("RVC2API_SERVER_DESCRIPTION", "RV-C to API Bridge"),
        "root_path": os.getenv("RVC2API_ROOT_PATH", ""),
    }


# ── Static File and Template Paths ─────────────────────────────────────────
def get_static_paths():
    """
    Resolves and returns paths to the web UI's static files and templates directories.

    It primarily uses `importlib.resources` to locate these directories, making it
    robust for packaged applications. If `importlib.resources` fails (e.g., in
    certain development or non-standard package structures), it falls back to
    a `__file__`-based method to determine paths relative to this config.py file.

    Logs errors if paths cannot be resolved or are invalid.

    Returns:
        dict: A dictionary with keys 'web_ui_dir', 'static_dir', and 'templates_dir',
              containing the absolute paths to these directories.
    """
    static_dir_path_str = None
    templates_dir_path_str = None
    web_ui_dir_path_str = None

    try:
        module_logger.info("Attempting to get static paths using importlib.resources...")

        # For 'core_daemon.web_ui.static'
        static_files_traversable = importlib.resources.files("core_daemon.web_ui.static")
        if static_files_traversable.is_dir():
            static_dir_path_str = str(static_files_traversable)
            module_logger.info(f"importlib.resources resolved static_dir: {static_dir_path_str}")
        else:
            module_logger.error(
                "'core_daemon.web_ui.static' resolved by importlib.resources is not a directory."
            )
            raise ValueError(
                "'core_daemon.web_ui.static' is not a directory via importlib.resources"
            )

        # For 'core_daemon.web_ui.templates'
        templates_files_traversable = importlib.resources.files("core_daemon.web_ui.templates")
        if templates_files_traversable.is_dir():
            templates_dir_path_str = str(templates_files_traversable)
            module_logger.info(
                f"importlib.resources resolved templates_dir: {templates_dir_path_str}"
            )
        else:
            module_logger.error(
                "'core_daemon.web_ui.templates' resolved by importlib.resources is not a directory."
            )
            raise ValueError(
                "'core_daemon.web_ui.templates' is not a directory via importlib.resources"
            )

        # For 'core_daemon.web_ui' (parent)
        web_ui_files_traversable = importlib.resources.files("core_daemon.web_ui")
        if web_ui_files_traversable.is_dir():
            web_ui_dir_path_str = str(web_ui_files_traversable)
            module_logger.info(f"importlib.resources resolved web_ui_dir: {web_ui_dir_path_str}")
        elif static_dir_path_str:  # Try to derive from static_dir if direct web_ui fails
            web_ui_dir_path_str = os.path.dirname(static_dir_path_str)
            module_logger.info(
                f"Derived web_ui_dir from static_dir"
                f"('{static_dir_path_str}'): {web_ui_dir_path_str}"
            )
        else:
            module_logger.error(
                "'core_daemon.web_ui' not resolved as a directory and could not be derived."
            )
            raise ValueError("'core_daemon.web_ui' is not a directory via importlib.resources")

        if not all([static_dir_path_str, templates_dir_path_str, web_ui_dir_path_str]):
            # This case should ideally be caught by earlier ValueErrors
            module_logger.error("Failed to resolve one or more paths using importlib.resources.")
            raise ValueError("Path resolution failed with importlib.resources")

    except Exception as e:
        module_logger.error(
            f"Error using importlib.resources ('{e}')."
            f"Falling back to __file__-based path resolution.",
            exc_info=True,
        )

        current_file_path = os.path.abspath(__file__)
        module_logger.info(
            f"Fallback: current_file_path (__file__ for config.py): {current_file_path}"
        )
        core_daemon_dir = os.path.dirname(current_file_path)
        module_logger.info(f"Fallback: core_daemon_dir (parent of config.py): {core_daemon_dir}")

        web_ui_dir_path_str = os.path.join(core_daemon_dir, "web_ui")
        static_dir_path_str = os.path.join(web_ui_dir_path_str, "static")
        templates_dir_path_str = os.path.join(web_ui_dir_path_str, "templates")

        module_logger.info(f"Fallback resolved web_ui_dir: {web_ui_dir_path_str}")
        module_logger.info(f"Fallback resolved static_dir: {static_dir_path_str}")
        module_logger.info(f"Fallback resolved templates_dir: {templates_dir_path_str}")

    # Final validation of determined paths
    if not static_dir_path_str or not os.path.isdir(static_dir_path_str):
        module_logger.critical(
            f"CRITICAL FAILURE: Final static_dir ('{static_dir_path_str}')"
            f"is invalid or not a directory. Static files will likely fail to serve."
        )
    else:
        module_logger.info(f"Final static_dir to be used: {static_dir_path_str}")

    if not templates_dir_path_str or not os.path.isdir(templates_dir_path_str):
        module_logger.critical(
            f"CRITICAL FAILURE: Final templates_dir ('{templates_dir_path_str}')"
            f"is invalid or not a directory. Templates will likely fail to load."
        )
    else:
        module_logger.info(f"Final templates_dir to be used: {templates_dir_path_str}")

    if not web_ui_dir_path_str or not os.path.isdir(
        web_ui_dir_path_str
    ):  # Check if web_ui_dir is valid
        module_logger.warning(
            f"Warning: Final web_ui_dir ('{web_ui_dir_path_str}') is invalid or not a directory."
        )
    else:
        module_logger.info(f"Final web_ui_dir to be used: {web_ui_dir_path_str}")

    return {
        "web_ui_dir": web_ui_dir_path_str,
        "static_dir": static_dir_path_str,
        "templates_dir": templates_dir_path_str,
    }


# ── CAN Bus Configuration ─────────────────────────────────────────────────
def get_canbus_config():
    """
    Retrieves CAN bus configuration settings from environment variables.

    Returns:
        dict: A dictionary containing:
              - 'channels': A list of CAN interface names (e.g., ['can0', 'can1']).
              - 'bustype': The CAN bus type (e.g., 'socketcan').
              - 'bitrate': The CAN bus bitrate as an integer.
    """
    return {
        "channels": os.getenv("CAN_CHANNELS", "can0,can1").split(","),
        "bustype": os.getenv("CAN_BUSTYPE", "socketcan"),
        "bitrate": int(os.getenv("CAN_BITRATE", "500000")),
    }
