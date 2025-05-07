import os
import logging

# Add logger initialization at the top of the file
logger = logging.getLogger(__name__)


# ── Logging Configuration ──────────────────────────────────────────────────
def configure_logger():
    logger = logging.getLogger()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = "%(asctime)s %(name)s[%(process)d] %(levelname)s %(message)s"

    logging.basicConfig(level=log_level, format=log_format)
    logger.setLevel(logging.DEBUG)  # Ensure logger processes DEBUG messages for handlers

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
