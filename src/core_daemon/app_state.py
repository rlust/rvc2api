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
    global light_entity_ids, light_command_info, decoder_map, entity_id_lookup

    now = time.time()
    logger.info(f"Pre-seeding states for {len(light_entity_ids)} light entities.")
    for eid in light_entity_ids:
        info = light_command_info.get(eid)
        if not info:
            logger.warning(f"Pre-seeding: No command info for light entity ID: {eid}")
            continue

        spec_entry = None
        target_dgn_hex = format(info["dgn"], "X").upper()
        for entry_val in decoder_map.values():
            if entry_val.get("dgn_hex", "").upper() == target_dgn_hex:
                spec_entry = entry_val
                break

        if not spec_entry:
            logger.warning(
                f"Pre-seeding: No spec entry found for DGN {target_dgn_hex} (from light {eid})"
            )
            continue

        decoded, raw = decode_payload_func(spec_entry, bytes([0] * 8))

        brightness = raw.get("operating_status", 0)
        human_state = "on" if brightness > 0 else "off"
        lookup = entity_id_lookup.get(eid, {})

        payload = {
            "entity_id": eid,
            "value": decoded,
            "raw": raw,
            "state": human_state,
            "timestamp": now,
            "suggested_area": lookup.get("suggested_area", "Unknown"),
            "device_type": lookup.get(
                "device_type", "light"
            ),  # Default to 'light' for these entities
            "capabilities": lookup.get("capabilities", []),
            "friendly_name": lookup.get("friendly_name"),
            "groups": lookup.get("groups", []),
        }
        update_entity_state_and_history(eid, payload)
    logger.info("Finished pre-seeding light states.")
