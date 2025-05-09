"""
Manages the in-memory application state for the rvc2api daemon.

This module holds the current state of all entities, their historical data,
and configuration-derived lookups (like entity definitions, light commands, etc.).
It provides functions to initialize, update, and access this shared state.
"""

import logging
import time
from collections import deque
from typing import Any, Callable, Dict, List, Set  # Added Set

from fastapi import WebSocket  # Added WebSocket for type hinting

# Import metrics that are directly related to the state managed here
from core_daemon.metrics import ENTITY_COUNT, HISTORY_SIZE_GAUGE

# Assuming UnmappedEntryModel is in core_daemon.models
# We need to import it if it's used in type hints for unmapped_entries
from core_daemon.models import UnknownPGNEntry, UnmappedEntryModel

# In-memory state - holds the most recent data payload for each entity_id
state: Dict[str, Dict[str, Any]] = {}

# History duration
HISTORY_DURATION: int = 24 * 3600  # seconds

# History data structure (initialized empty, to be populated by initialize_history_deques)
history: Dict[str, deque[Dict[str, Any]]] = {}

# Initialize logger
logger = logging.getLogger(__name__)

# Unmapped entries
unmapped_entries: Dict[str, UnmappedEntryModel] = {}

# Unknown PGNs (PGNs not found in rvc.json spec)
unknown_pgns: Dict[str, UnknownPGNEntry] = {}

# Last known brightness levels for lights
last_known_brightness_levels: Dict[str, int] = {}

# Configuration data loaded at startup, to be populated by initialize_app_from_config
entity_id_lookup: Dict[str, Any] = {}
light_entity_ids: List[str] = []
light_command_info: Dict[str, Any] = {}
decoder_map: Dict[int, Any] = {}
raw_device_mapping: Dict[str, Any] = {}
device_lookup: Dict[tuple, Any] = {}
status_lookup: Dict[tuple, Any] = {}
pgn_hex_to_name_map: Dict[str, str] = {}

# WebSocket client sets - moved here from websocket.py for central state management
clients: Set[WebSocket] = set()
log_ws_clients: Set[WebSocket] = set()


def initialize_app_from_config(config_data_tuple: tuple, decode_payload_function: Callable) -> None:
    """
    Initializes all configuration-derived application state.
    This function populates global variables within this module and then
    calls further initialization functions like initialize_history_deques
    and preseed_light_states.
    """
    global decoder_map, raw_device_mapping, device_lookup, status_lookup
    global light_entity_ids, entity_id_lookup, light_command_info, pgn_hex_to_name_map

    (
        decoder_map_val,
        raw_device_mapping_val,
        device_lookup_val,
        status_lookup_val,
        light_entity_ids_val,
        entity_id_lookup_val,
        light_command_info_val,
        pgn_hex_to_name_map_val,
    ) = config_data_tuple

    decoder_map = decoder_map_val
    raw_device_mapping = raw_device_mapping_val
    device_lookup = device_lookup_val
    status_lookup = status_lookup_val
    light_entity_ids = light_entity_ids_val
    entity_id_lookup = entity_id_lookup_val
    light_command_info = light_command_info_val
    pgn_hex_to_name_map = pgn_hex_to_name_map_val

    logger.info("Application state populated from configuration data.")

    initialize_history_deques_internal()
    preseed_light_states_internal(decode_payload_function)


def get_last_known_brightness(entity_id: str) -> int:
    """
    Retrieves the last known brightness for a given light entity.
    Defaults to 100 (full brightness) if not previously set.
    """
    return last_known_brightness_levels.get(entity_id, 100)


def set_last_known_brightness(entity_id: str, brightness: int) -> None:
    """
    Sets the last known brightness for a given light entity.
    Brightness should be an integer between 0 and 100.
    """
    last_known_brightness_levels[entity_id] = brightness


def initialize_history_deques_internal() -> None:
    """
    Initializes the history dictionary with empty deques for each entity ID.
    This should be called after entity_id_lookup is populated globally in this module.
    """
    global history, entity_id_lookup
    for eid in entity_id_lookup:
        if eid not in history:
            history[eid] = deque()
    logger.info("History deques initialized for all entities.")


def update_entity_state_and_history(entity_id: str, payload_to_store: Dict[str, Any]) -> None:
    """
    Updates the state and history for a given entity and updates relevant metrics.

    Args:
        entity_id: The ID of the entity to update.
        payload_to_store: The complete payload dictionary to store in state and history.
    """
    global state, history, HISTORY_DURATION  # Allow modification of global state variables

    # Update current state
    state[entity_id] = payload_to_store
    ENTITY_COUNT.set(len(state))

    # Update history
    if entity_id in history:  # Should always be true if initialize_history_deques was called
        history_deque = history[entity_id]
        history_deque.append(payload_to_store)
        current_time = payload_to_store.get(
            "timestamp", time.time()
        )  # Use payload's timestamp or current time
        cutoff = current_time - HISTORY_DURATION
        while history_deque and history_deque[0]["timestamp"] < cutoff:
            history_deque.popleft()
        HISTORY_SIZE_GAUGE.labels(entity_id=entity_id).set(len(history_deque))
    else:
        # This case should ideally not be reached if entities are pre-initialized in history
        # However, as a fallback, create a new deque
        history[entity_id] = deque([payload_to_store])
        HISTORY_SIZE_GAUGE.labels(entity_id=entity_id).set(1)
        # Consider logging a warning if an entity_id is not found in history initially
        logger.warning(f"History deque not found for {entity_id}, created new one.")


def preseed_light_states_internal(decode_payload_func: Callable) -> None:
    """
    Initializes the state and history for all known light entities to an "off" state at startup.
    Uses global state variables like light_entity_ids, light_command_info, decoder_map,
    and entity_id_lookup.
    """
    global light_entity_ids, light_command_info, decoder_map, entity_id_lookup, state

    now = time.time()
    logger.info(f"Pre-seeding states for {len(light_entity_ids)} light entities.")
    for eid in light_entity_ids:
        info = light_command_info.get(eid)
        entity_config = entity_id_lookup.get(eid)

        if not info or not entity_config:
            logger.warning(f"Pre-seeding: Missing info or entity_config for light entity ID: {eid}")
            continue

        # Determine DGN for status pre-seeding:
        # Prefer status_dgn (hex string from YAML) if available.
        # Else, use the DGN from command_info (integer, under which the light is
        # defined in mapping).
        dgn_for_status_hex_str = None
        raw_status_dgn_from_config = entity_config.get("status_dgn")

        if raw_status_dgn_from_config:
            dgn_for_status_hex_str = str(raw_status_dgn_from_config).upper().replace("0X", "")
        else:
            # Fallback to the DGN the light is defined under (for commands)
            dgn_for_status_hex_str = format(info["dgn"], "X").upper()

        logger.debug(f"Pre-seeding {eid}: Using DGN {dgn_for_status_hex_str} for initial status.")

        spec_entry = None
        # Search decoder_map using the determined DGN hex string
        # decoder_map values are dictionaries from rvc.json, which contain 'dgn_hex'
        for entry_val in decoder_map.values():
            if entry_val.get("dgn_hex", "").upper().replace("0X", "") == dgn_for_status_hex_str:
                spec_entry = entry_val
                break

        if not spec_entry:
            logger.warning(
                f"Pre-seeding: No spec entry found for DGN {dgn_for_status_hex_str} (entity: {eid})"
            )
            continue

        # Assume an all-zero payload means "off" for pre-seeding
        # The length of the data should match the spec_entry's expected data length if available,
        # otherwise default to 8 bytes.
        data_length = spec_entry.get("data_length", 8)  # Assuming spec_entry might have data_length
        initial_can_payload = bytes([0] * data_length)

        decoded, raw = decode_payload_func(spec_entry, initial_can_payload)

        brightness = raw.get(
            "operating_status", 0
        )  # This might need adjustment based on actual decoded data
        human_state = "on" if brightness > 0 else "off"
        # Ensure 'lookup' is the entity_config itself, which was already fetched
        # lookup = entity_id_lookup.get(eid, {}) # This is redundant

        payload = {
            "entity_id": eid,
            "value": decoded,
            "raw": raw,
            "state": human_state,
            "timestamp": now,
            "suggested_area": entity_config.get("suggested_area", "Unknown"),
            "device_type": entity_config.get(
                "device_type", "light"
            ),  # Default to 'light' for these entities
            "capabilities": entity_config.get("capabilities", []),
            "friendly_name": entity_config.get("friendly_name"),
            "groups": entity_config.get("groups", []),
        }
        update_entity_state_and_history(eid, payload)
    logger.info("Finished pre-seeding light states.")
