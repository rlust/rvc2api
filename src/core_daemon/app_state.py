import logging
import time
from collections import deque
from typing import Any, Callable, Dict, List  # Added List

# Import metrics that are directly related to the state managed here
from core_daemon.metrics import ENTITY_COUNT, HISTORY_SIZE_GAUGE

# Assuming UnmappedEntryModel is in core_daemon.models
# We need to import it if it's used in type hints for unmapped_entries
from core_daemon.models import UnmappedEntryModel

# In-memory state
state: Dict[str, Dict[str, Any]] = {}

# History duration
HISTORY_DURATION: int = 24 * 3600  # seconds

# History data structure (initialized empty, to be populated by initialize_history_deques)
history: Dict[str, deque[Dict[str, Any]]] = {}

# Initialize logger
logger = logging.getLogger(__name__)

# Unmapped entries
unmapped_entries: Dict[str, UnmappedEntryModel] = {}

# Last known brightness levels for lights
last_known_brightness_levels: Dict[str, int] = {}

# Configuration data loaded at startup, to be populated by main.py
entity_id_lookup: Dict[str, Any] = {}
light_entity_ids: List[str] = []
light_command_info: Dict[str, Any] = {}
# Potentially others if needed by routers/modules directly from app_state:
# decoder_map: Dict[int, Any] = {}
# raw_device_mapping: Dict[str, Any] = {}
# device_lookup: Dict[tuple, Any] = {}
# status_lookup: Dict[tuple, Any] = {}
# pgn_hex_to_name_map: Dict[str, str] = {}


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


def initialize_history_deques(entity_id_lookup: Dict[str, Any]) -> None:
    """
    Initializes the history dictionary with empty deques for each entity ID.
    This should be called after entity_id_lookup is populated.
    """
    global history
    for eid in entity_id_lookup:
        if (
            eid not in history
        ):  # Ensure we don't overwrite if called multiple times (though unlikely)
            history[eid] = deque()


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


def preseed_light_states(
    light_entity_ids: list[str],
    light_command_info: dict[str, Any],
    decoder_map_values: list[dict[str, Any]],  # Effectively list(decoder_map.values())
    entity_id_lookup: dict[str, Any],
    decode_payload_func: Callable,  # e.g., from rvc_decoder.decode_payload
) -> None:
    """
    Initializes the state and history for all known light entities to an "off" state at startup.
    This ensures that lights appear in the API with a defined state even before any CAN messages.
    Uses the existing update_entity_state_and_history function to ensure consistency.
    """
    now = time.time()
    for eid in light_entity_ids:
        info = light_command_info.get(eid)
        if not info:
            # Optionally, add logging here if a configured light_entity_id has no command_info
            # logger.warning(f"Pre-seeding: No command info for light entity ID: {eid}")
            continue

        spec_entry = None
        # info["dgn"] should be the PGN for the light's command.
        # We need to find a spec entry (typically for a status DGN) that matches this PGN
        # to decode a generic "off" payload.
        target_dgn_hex = format(info["dgn"], "X").upper()
        for entry_val in decoder_map_values:
            if entry_val.get("dgn_hex", "").upper() == target_dgn_hex:
                spec_entry = entry_val
                break

        if not spec_entry:
            # Optionally, add logging here
            logger.warning(
                f"Pre-seeding: No spec entry found for DGN {target_dgn_hex} (from light {eid})"
            )
            continue

        # Use a generic 8-byte zero payload, which usually signifies an "off" or default state.
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
    # Metrics (ENTITY_COUNT, HISTORY_SIZE_GAUGE) are updated within update_entity_state_and_history.
