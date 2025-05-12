"""
Defines FastAPI APIRouter for managing and interacting with RV-C entities.

This module includes routes for:
- Listing all entities with optional filtering by type or area.
- Retrieving details and history for specific entities.
- Listing unmapped DGN/instance pairs observed on the CAN bus.
- Listing and controlling light entities, both individually and in bulk.
- Providing metadata about available entity types, areas, capabilities, and commands.
"""

import json
import logging
import time
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

# Application state and helpers
from core_daemon.app_state import unknown_pgns  # Import unknown_pgns
from core_daemon.app_state import unmapped_entries  # Ensure unmapped_entries is imported
from core_daemon.app_state import (
    entity_id_lookup,
    get_last_known_brightness,
    history,
    light_command_info,
    set_last_known_brightness,
    state,
    update_entity_state_and_history,
)

# CAN specific components
from core_daemon.can_manager import can_tx_queue, create_light_can_message

# Metrics
from core_daemon.metrics import CAN_TX_ENQUEUE_LATENCY, CAN_TX_ENQUEUE_TOTAL, CAN_TX_QUEUE_LENGTH

# Models
from core_daemon.models import UnknownPGNEntry  # Import UnknownPGNEntry
from core_daemon.models import ControlCommand, ControlEntityResponse, Entity, UnmappedEntryModel

# WebSocket for broadcasting updates
from core_daemon.websocket import broadcast_to_clients

logger = logging.getLogger(__name__)

api_router_entities = APIRouter()  # FastAPI router for entity-related API endpoints


@api_router_entities.get("/entities", response_model=Dict[str, Entity])
async def list_entities(
    device_type: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
):
    """
    Return all entities, optionally filtered by device_type and/or area.

    Args:
        device_type: Optional filter by entity device_type.
        area: Optional filter by entity suggested_area.

    Returns:
        A dictionary of entities matching the filter criteria.
    """

    def matches(eid: str) -> bool:
        """Helper function to check if an entity matches the filter criteria."""
        cfg = entity_id_lookup.get(eid, {})
        if device_type and cfg.get("device_type") != device_type:
            return False
        if area and cfg.get("suggested_area") != area:
            return False
        return True

    return {eid: ent for eid, ent in state.items() if matches(eid)}


@api_router_entities.get("/entities/ids", response_model=List[str])
async def list_entity_ids():
    """Return all known entity IDs."""
    return list(state.keys())


@api_router_entities.get("/entities/{entity_id}", response_model=Entity)
async def get_entity(entity_id: str):
    """
    Return the latest value for one entity.

    Args:
        entity_id: The ID of the entity to retrieve.

    Raises:
        HTTPException: If the entity is not found.

    Returns:
        The entity object.
    """
    ent = state.get(entity_id)
    if not ent:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ent


@api_router_entities.get("/entities/{entity_id}/history", response_model=List[Entity])
async def get_history(
    entity_id: str,
    since: Optional[float] = Query(
        None, description="Unix timestamp; only entries newer than this"
    ),
    limit: Optional[int] = Query(1000, ge=1, description="Max number of points to return"),
):
    """
    Return the history of an entity.

    Args:
        entity_id: The ID of the entity to retrieve history for.
        since: Optional Unix timestamp to filter entries newer than this.
        limit: Optional limit on the number of points to return.

    Raises:
        HTTPException: If the entity is not found.

    Returns:
        A list of entity history entries.
    """
    if entity_id not in history:
        raise HTTPException(status_code=404, detail="Entity not found")
    entries = list(history[entity_id])
    if since is not None:
        entries = [e for e in entries if e["timestamp"] > since]

    actual_limit = limit if limit is not None else 1000
    return entries[-actual_limit:]


@api_router_entities.get("/unmapped_entries", response_model=Dict[str, UnmappedEntryModel])
async def get_unmapped_entries_api():  # Renamed function for clarity
    """
    Return all DGN/instance pairs that were seen on the bus but not mapped in device_mapping.yml.

    Returns:
        A dictionary of unmapped DGN/instance pairs.
    """
    return unmapped_entries  # Ensure this uses the imported app_state.unmapped_entries


@api_router_entities.get("/unknown_pgns", response_model=Dict[str, UnknownPGNEntry])
async def get_unknown_pgns_api():
    """
    Return all CAN messages whose PGN (from arbitration ID) was not found in the rvc.json spec.

    Returns:
        A dictionary of unknown PGNs.
    """
    return unknown_pgns


@api_router_entities.get("/meta", response_model=Dict[str, List[str]])
async def metadata():
    """
    Expose groupable dimensions:
    - type        (device_type)
    - area        (suggested_area)
    - capability  (defined in mapping)
    - command     (derived from capabilities)
    - groups      (defined in mapping)

    Returns:
        A dictionary of metadata about available entity types, areas, capabilities, and commands.
    """
    mapping = {
        "type": "device_type",
        "area": "suggested_area",
        "capability": "capabilities",
        "groups": "groups",
    }
    out: Dict[str, List[str]] = {}

    for public, internal in mapping.items():
        values = set()
        for cfg in entity_id_lookup.values():
            val = cfg.get(internal)
            if isinstance(val, list):
                values.update(val)
            elif val is not None:
                values.add(val)
        out[public] = sorted(list(values))  # Ensure 'groups' is also processed here

    command_set = set()
    for eid, cfg in entity_id_lookup.items():
        if eid in light_command_info:  # Check if it's a controllable light
            caps = cfg.get("capabilities", [])
            command_set.add("set")  # Always available for lights
            command_set.add("toggle")  # Always available for lights
            if "on_off" in caps:  # Though set/toggle cover this, it can be explicit
                command_set.add("on_off")
            if "brightness" in caps:
                command_set.add("brightness")
                command_set.add("brightness_up")  # Or brightness_increase
                command_set.add("brightness_down")  # Or brightness_decrease
    out["command"] = sorted(list(command_set))

    for key in ["type", "area", "capability", "command", "groups"]:
        out.setdefault(key, [])
    return out


async def _send_light_can_command(
    entity_id: str, target_brightness_ui: int, action_description: str
) -> bool:
    """
    Internal helper to construct and send a CAN command for a light entity.

    This function takes the entity ID, target brightness (0-100 scale),
    and an action description. It looks up the necessary CAN parameters
    (PGN, instance, interface) from `light_command_info`.
    It then creates the CAN message, queues it for transmission, and performs
    an optimistic update of the entity's state in `app_state` and broadcasts
    this update via WebSockets.

    Args:
        entity_id: The ID of the light entity to control.
        target_brightness_ui: The desired brightness level (0-100).
        action_description: A string describing the action being taken (for logging).

    Returns:
        True if the CAN message was successfully queued, False otherwise.
    """
    if entity_id not in light_command_info:
        logger.error(
            f"Control Error: {entity_id} not found in light_command_info for "
            f"action '{action_description}'."
        )
        return False

    info = light_command_info[entity_id]
    pgn = info["dgn"]
    instance = info["instance"]
    interface = info["interface"]
    brightness_can_level = min(target_brightness_ui * 2, 0xC8)
    msg = create_light_can_message(pgn, instance, brightness_can_level)

    logger.info(
        f"CAN CMD OUT (Helper): entity_id={entity_id}, "
        f"arbitration_id=0x{msg.arbitration_id:08X}, "
        f"data={msg.data.hex().upper()}, instance={instance}, "
        f"action='{action_description}'"
    )
    try:
        with CAN_TX_ENQUEUE_LATENCY.time():
            await can_tx_queue.put((msg, interface))
            CAN_TX_ENQUEUE_TOTAL.inc()
        CAN_TX_QUEUE_LENGTH.set(can_tx_queue.qsize())
        logger.info(
            f"CAN CMD Queued (Helper): '{action_description}' for {entity_id} "
            f"(CAN Lvl: {brightness_can_level}) -> {interface}"
        )

        optimistic_state_str = "on" if target_brightness_ui > 0 else "off"
        optimistic_raw_val = {
            "operating_status": brightness_can_level,
            "instance": instance,
            "group": 0x7C,  # Default group for light commands
        }
        optimistic_value_val = {
            "operating_status": str(target_brightness_ui),  # UI scale
            "instance": str(instance),
            "group": str(0x7C),
        }
        ts = time.time()
        lookup = entity_id_lookup.get(entity_id, {})
        optimistic_payload_to_store = {
            "entity_id": entity_id,
            "value": optimistic_value_val,
            "raw": optimistic_raw_val,
            "state": optimistic_state_str,
            "timestamp": ts,
            "suggested_area": lookup.get(
                "suggested_area", state.get(entity_id, {}).get("suggested_area", "Unknown")
            ),
            "device_type": lookup.get(
                "device_type", state.get(entity_id, {}).get("device_type", "light")
            ),
            "capabilities": lookup.get(
                "capabilities", state.get(entity_id, {}).get("capabilities", [])
            ),
            "friendly_name": lookup.get(
                "friendly_name", state.get(entity_id, {}).get("friendly_name")
            ),
            "groups": lookup.get("groups", state.get(entity_id, {}).get("groups", [])),
        }
        update_entity_state_and_history(entity_id, optimistic_payload_to_store)
        text = json.dumps(optimistic_payload_to_store)
        await broadcast_to_clients(text)
        return True
    except Exception as e:
        logger.error(
            f"Failed to enqueue or optimistically update CAN control for {entity_id} "
            f"(Action: '{action_description}'): {e}",
            exc_info=True,
        )
        return False


@api_router_entities.post("/entities/{entity_id}/control", response_model=ControlEntityResponse)
async def control_entity(
    entity_id: str,
    cmd: ControlCommand = Body(
        ...,
        examples={
            "turn_on": {"summary": "Turn light on", "value": {"command": "set", "state": "on"}},
            "turn_off": {"summary": "Turn light off", "value": {"command": "set", "state": "off"}},
            "set_brightness": {
                "summary": "Set brightness to 75%",
                "value": {"command": "set", "state": "on", "brightness": 75},
            },
            "toggle": {"summary": "Toggle current state", "value": {"command": "toggle"}},
            "brightness_up": {
                "summary": "Increase brightness by 10%",
                "value": {"command": "brightness_up"},  # Changed from brightness_increase
            },
            "brightness_down": {
                "summary": "Decrease brightness by 10%",
                "value": {"command": "brightness_down"},  # Changed from brightness_decrease
            },
        },
    ),
) -> ControlEntityResponse:
    """
    Control a specific entity (light) by sending a command.

    Args:
        entity_id: The ID of the entity to control.
        cmd: The control command to execute.

    Raises:
        HTTPException: If the entity is not found or not controllable.

    Returns:
        A response indicating the status of the control command.
    """
    device = entity_id_lookup.get(entity_id)
    if not device:
        logger.debug(f"Control command for unknown entity_id: {entity_id}")
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity_id not in light_command_info:  # Check if it's a controllable light
        logger.debug(f"Control command for non-controllable entity_id: {entity_id}")
        raise HTTPException(status_code=400, detail="Entity is not controllable as a light")

    logger.info(
        f"HTTP CMD RX: entity_id='{entity_id}', command='{cmd.command}', "
        f"state='{cmd.state}', brightness='{cmd.brightness}'"
    )

    current_state_data = state.get(entity_id, {})
    current_on_str = current_state_data.get("state", "off")
    current_on = current_on_str.lower() == "on"
    current_raw_values = current_state_data.get("raw", {})
    current_brightness_raw = current_raw_values.get("operating_status", 0)
    current_brightness_ui = (
        min(int(current_brightness_raw) // 2, 100)
        if isinstance(current_brightness_raw, (int, float, str))
        and str(current_brightness_raw).isdigit()
        else (100 if current_on else 0)
    )

    last_brightness_ui = get_last_known_brightness(entity_id)

    logger.debug(
        f"Control for {entity_id}: current_on_str='{current_on_str}', "
        f"current_on={current_on}, current_brightness_ui={current_brightness_ui}%, "
        f"last_known_brightness_ui={last_brightness_ui}%"
    )

    target_brightness_ui = current_brightness_ui
    action = "No change"

    if cmd.command == "set":
        if cmd.state is not None and cmd.state not in {"on", "off"}:
            raise HTTPException(
                status_code=400, detail="State must be 'on' or 'off' for set command"
            )
        if cmd.state == "on":
            if cmd.brightness is not None:
                target_brightness_ui = cmd.brightness
            elif not current_on:
                target_brightness_ui = last_brightness_ui
            action = f"Set ON to {target_brightness_ui}%"
        elif cmd.state == "off":
            if current_on and current_brightness_ui > 0:
                set_last_known_brightness(entity_id, current_brightness_ui)
            target_brightness_ui = 0
            action = "Set OFF"
        elif cmd.brightness is not None:  # Setting brightness implies turning on
            target_brightness_ui = cmd.brightness
            action = f"Set Brightness to {target_brightness_ui}% (implies ON)"

    elif cmd.command == "toggle":
        if current_on:
            if current_brightness_ui > 0:
                set_last_known_brightness(entity_id, current_brightness_ui)
            target_brightness_ui = 0
            action = "Toggle OFF"
        else:
            target_brightness_ui = last_brightness_ui
            action = f"Toggle ON to {target_brightness_ui}%"

    elif cmd.command == "brightness_up":  # Was brightness_increase
        if not current_on and current_brightness_ui == 0:
            target_brightness_ui = 10
        else:
            target_brightness_ui = min(current_brightness_ui + 10, 100)
        action = f"Brightness UP to {target_brightness_ui}%"

    elif cmd.command == "brightness_down":  # Was brightness_decrease
        target_brightness_ui = max(current_brightness_ui - 10, 0)
        action = f"Brightness DOWN to {target_brightness_ui}%"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid command: {cmd.command}")

    if target_brightness_ui > 0:  # Store if light will be on
        set_last_known_brightness(entity_id, target_brightness_ui)

    if not await _send_light_can_command(entity_id, target_brightness_ui, action):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send CAN command for {entity_id} (Action: {action})",
        )

    return ControlEntityResponse(
        status="sent",
        entity_id=entity_id,
        command=cmd.command,
        state="on" if target_brightness_ui > 0 else "off",
        brightness=target_brightness_ui,
        action=action,
    )
