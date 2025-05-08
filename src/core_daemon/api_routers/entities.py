import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

# Application state and helpers
from core_daemon.app_state import (
    entity_id_lookup,
    get_last_known_brightness,
    history,
    light_command_info,
    light_entity_ids,
    set_last_known_brightness,
    state,
    unmapped_entries,  # Ensure unmapped_entries is imported
    update_entity_state_and_history,
)

# CAN specific components
from core_daemon.can_manager import can_tx_queue, create_light_can_message

# Metrics
from core_daemon.metrics import CAN_TX_ENQUEUE_LATENCY, CAN_TX_ENQUEUE_TOTAL, CAN_TX_QUEUE_LENGTH

# Models
from core_daemon.models import (
    BulkLightControlResponse,
    ControlCommand,
    ControlEntityResponse,
    Entity,
    UnmappedEntryModel,
)

# WebSocket for broadcasting updates
from core_daemon.websocket import broadcast_to_clients

logger = logging.getLogger(__name__)

api_router_entities = APIRouter()


@api_router_entities.get("/entities", response_model=Dict[str, Entity])
async def list_entities(
    type: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
):
    """
    Return all entities, optionally filtered by device_type and/or area.
    """

    def matches(eid: str) -> bool:
        cfg = entity_id_lookup.get(eid, {})
        if type and cfg.get("device_type") != type:
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
    """Return the latest value for one entity."""
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
    """
    return unmapped_entries  # Ensure this uses the imported app_state.unmapped_entries


@api_router_entities.get("/lights", response_model=Dict[str, Entity])
async def list_lights(
    state_filter: Optional[str] = Query(None, alias="state", description="Filter by 'on'/'off'"),
    capability: Optional[str] = Query(None, description="e.g. 'brightness' or 'on_off'"),
    area: Optional[str] = Query(None),
):
    """
    Return lights, optionally filtered by:
    - state (\'on\' or \'off\')
    - a specific capability (e.g. \'brightness\')
    - area (suggested_area)
    """
    results: Dict[str, Entity] = {}
    for eid, ent in state.items():
        if eid not in light_entity_ids:
            continue
        cfg = entity_id_lookup.get(eid, {})
        if cfg.get("device_type") != "light":
            continue
        if area and cfg.get("suggested_area") != area:
            continue
        caps = cfg.get("capabilities", [])
        if capability and capability not in caps:
            continue
        if state_filter:
            val = ent.get("state")
            if not val or val.strip().lower() != state_filter.strip().lower():
                continue
        results[eid] = Entity(**ent)
    return results


@api_router_entities.get("/meta", response_model=Dict[str, List[str]])
async def metadata():
    """
    Expose groupable dimensions:
    - type        (device_type)
    - area        (suggested_area)
    - capability  (defined in mapping)
    - command     (derived from capabilities)
    - groups      (defined in mapping)
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
    Helper function to construct, send a CAN command for a light, and perform optimistic update.
    Returns True if the command was successfully queued, False otherwise.
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


async def _bulk_control_lights(
    group_filter: Optional[str],
    command: str,
    state_cmd: Optional[str] = None,
    brightness_val: Optional[int] = None,
) -> List[Dict[str, Any]]:
    results = []
    action_description_base = f"Bulk {command}"
    if state_cmd:
        action_description_base += f" {state_cmd}"
    if brightness_val is not None:
        action_description_base += f" to {brightness_val}%"
    if group_filter:
        logger.info(
            f"Processing bulk command for group: {group_filter}, command: {command}, "
            f"state: {state_cmd}, brightness: {brightness_val}"
        )
    else:
        logger.info(
            f"Processing bulk command for ALL lights, command: {command}, "
            f"state: {state_cmd}, brightness: {brightness_val}"
        )

    controlled_entity_ids = set()

    for entity_id, entity_config in entity_id_lookup.items():
        if entity_id in controlled_entity_ids:
            continue

        is_light_entity = (
            entity_id in light_entity_ids or entity_config.get("device_type") == "light"
        )
        is_controllable_light = entity_id in light_command_info and is_light_entity

        if not is_controllable_light:
            continue

        if group_filter:
            entity_groups = entity_config.get("groups", [])
            # Ensure entity_groups is a list for the 'in' operator
            if not isinstance(entity_groups, list):
                entity_groups = [entity_groups] if entity_groups else []
            if group_filter not in entity_groups:
                continue

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

        target_brightness_ui = current_brightness_ui
        action_suffix = ""

        if command == "set":
            if state_cmd is not None and state_cmd not in {"on", "off"}:
                results.append(
                    {
                        "entity_id": entity_id,
                        "status": "error",
                        "detail": "State must be 'on' or 'off'",
                    }
                )
                continue
            if state_cmd == "on":
                if brightness_val is not None:
                    target_brightness_ui = brightness_val
                elif not current_on:
                    target_brightness_ui = last_brightness_ui
                action_suffix = f"ON to {target_brightness_ui}%"
            elif state_cmd == "off":
                if current_on and current_brightness_ui > 0:
                    set_last_known_brightness(entity_id, current_brightness_ui)
                target_brightness_ui = 0
                action_suffix = "OFF"
            elif brightness_val is not None:  # Setting brightness implies ON
                target_brightness_ui = brightness_val
                action_suffix = f"Brightness to {target_brightness_ui}% (implies ON)"

        elif command == "toggle":
            if current_on:
                if current_brightness_ui > 0:
                    set_last_known_brightness(entity_id, current_brightness_ui)
                target_brightness_ui = 0
                action_suffix = "Toggle OFF"
            else:
                target_brightness_ui = last_brightness_ui
                action_suffix = f"Toggle ON to {target_brightness_ui}%"

        elif command == "brightness_up":
            if not current_on and current_brightness_ui == 0:
                target_brightness_ui = 10
            else:
                target_brightness_ui = min(current_brightness_ui + 10, 100)
            action_suffix = f"Brightness UP to {target_brightness_ui}%"

        elif command == "brightness_down":
            target_brightness_ui = max(current_brightness_ui - 10, 0)
            action_suffix = f"Brightness DOWN to {target_brightness_ui}%"
        else:
            results.append(
                {"entity_id": entity_id, "status": "error", "detail": f"Invalid command: {command}"}
            )
            continue

        full_action_description = f"{action_description_base} ({action_suffix}) for {entity_id}"

        if target_brightness_ui > 0:
            set_last_known_brightness(entity_id, target_brightness_ui)

        success = await _send_light_can_command(
            entity_id, target_brightness_ui, full_action_description
        )
        results.append(
            {
                "entity_id": entity_id,
                "status": "sent" if success else "error",
                "action": full_action_description,
                "state": "on" if target_brightness_ui > 0 else "off",
                "brightness": target_brightness_ui,
            }
        )
        controlled_entity_ids.add(entity_id)

    if (
        not controlled_entity_ids and group_filter
    ):  # Only log warning if a filter was applied and nothing matched
        logger.warning(
            f"Bulk control command ({action_description_base}) did not match any lights "
            f"for group_filter: '{group_filter}'."
        )
    elif (
        not controlled_entity_ids and not group_filter
    ):  # Log if no lights controlled when targeting all
        logger.info(
            f"Bulk control command ({action_description_base}) targeted all lights,"
            f"but no controllable lights found or processed."
        )

    return results


@api_router_entities.post("/lights/control", response_model=BulkLightControlResponse)
async def control_lights_bulk(
    cmd: ControlCommand = Body(...),
    group: Optional[str] = Query(
        None, description="Group to control (e.g., 'interior', 'all')"  # Shortened description
    ),
):
    """
    Control multiple lights based on a group or all lights if no group is specified.
    The special group 'all' explicitly targets all controllable lights.
    If group is None or empty, it also targets all controllable lights.
    """
    logger.info(
        f"HTTP Bulk CMD RX: group='{group}', command='{cmd.command}', "
        f"state='{cmd.state}', brightness='{cmd.brightness}'"
    )

    # Treat group=None, group="", or group="all" as targeting all lights by passing None to helper
    effective_group_filter = group if group and group.lower() != "all" else None

    results = await _bulk_control_lights(
        group_filter=effective_group_filter,
        command=cmd.command,
        state_cmd=cmd.state,
        brightness_val=cmd.brightness,
    )

    lights_processed = len(results)
    lights_commanded_successfully = sum(1 for r in results if r.get("status") == "sent")
    errors = [r for r in results if r.get("status") == "error"]

    if lights_processed == 0:
        message = f"No lights found or matched the specified criteria (group: {group})."
        if effective_group_filter is None and group is None:  # Explicitly "all" or no group given
            message = "No controllable lights found in the system."
        elif effective_group_filter is None and group and group.lower() == "all":
            message = "No controllable lights for group 'all'."  # Further shortened

        return BulkLightControlResponse(
            status="no_match",
            message=message,
            action=cmd.command,
            group=group,
            lights_processed=0,
            lights_commanded=0,
            errors=[],
            details=[],
        )

    overall_status = "success"
    if errors:
        overall_status = "partial_error" if lights_commanded_successfully > 0 else "error"

    return BulkLightControlResponse(
        status=overall_status,
        message="Bulk command processing complete.",
        action=cmd.command,
        group=group,
        lights_processed=lights_processed,
        lights_commanded=lights_commanded_successfully,  # Changed to keyword argument
        errors=[
            {"entity_id": e.get("entity_id"), "detail": e.get("detail", "Unknown error")}
            for e in errors
        ],
        details=results,
    )
