"""
Defines FastAPI APIRouter for CAN bus related operations.

This module includes routes to get the status of CAN interfaces,
check the CAN transmit queue, and potentially other CAN-specific actions.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List

from fastapi import APIRouter

# Assuming can_tx_queue is in core_daemon.can_manager
from core_daemon.can_manager import can_tx_queue

# Assuming get_canbus_config is in core_daemon.config
from core_daemon.config import get_canbus_config

# Assuming CANInterfaceStats model is in core_daemon.models
from core_daemon.models import CANInterfaceStats

logger = logging.getLogger(__name__)

api_router_can = APIRouter()  # FastAPI router for CAN-related endpoints


@api_router_can.get("/can/status", response_model=List[CANInterfaceStats])
async def get_can_status():
    """
    Retrieves the status of configured CAN interfaces.
    Uses 'ip' command to get details like state, bitrate, and error counters.
    """
    can_config = get_canbus_config()
    interfaces_config = can_config.get(
        "channels", []
    )  # Corrected key from "interfaces" to "channels"
    status_list = []

    if not interfaces_config:
        logger.info("CAN status endpoint: No CAN interfaces configured (empty 'channels' list).")
        # Return empty list or raise HTTPException, depending on desired behavior for no channels
        return []  # Or raise HTTPException(status_code=404, detail="No CAN interfaces configured")

    for (
        iface_name
    ) in interfaces_config:  # Iterate directly over names if interfaces_config is a list of strings
        if not iface_name:
            continue

        try:
            # Check basic link status (UP/DOWN)
            proc_link_show = await asyncio.create_subprocess_shell(
                f"/run/current-system/sw/bin/ip link show {iface_name}",  # Use explicit path
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_link, stderr_link = await proc_link_show.communicate()

            if proc_link_show.returncode != 0:
                logger.error(f"Error getting link status for {iface_name}: {stderr_link.decode()}")
                is_up = False
            else:
                link_output = stdout_link.decode()
                is_up = "state UP" in link_output or "state UNKNOWN" in link_output

            # Get detailed information (bitrate, state, error counters)
            proc_details = await asyncio.create_subprocess_shell(
                f"/run/current-system/sw/bin/ip -details link show {iface_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_details, stderr_details = await proc_details.communicate()

            if proc_details.returncode != 0:
                logger.error(
                    f"Error getting detailed status for {iface_name}: {stderr_details.decode()}"
                )
                status_list.append(CANInterfaceStats(interface_name=iface_name, is_up=is_up))
                continue

            details_output = stdout_details.decode()
            stats = CANInterfaceStats(interface_name=iface_name, is_up=is_up)

            bitrate_match = re.search(r"bitrate (\\d+)", details_output)
            if bitrate_match:
                stats.bitrate = int(bitrate_match.group(1))

            state_match = re.search(
                r"state (ERROR-ACTIVE|ERROR-WARNING|ERROR-PASSIVE|BUS-OFF)", details_output
            )
            if state_match:
                stats.state = state_match.group(1)
            elif is_up:
                stats.state = "ACTIVE"

            errors_match = re.search(
                r"tx_errors (\\d+) rx_errors (\\d+)", details_output, re.MULTILINE
            )
            if not errors_match:
                errors_match = re.search(r"berr-counter tx (\\d+) rx (\\d+)", details_output)

            if errors_match:
                stats.error_counters = {
                    "tx_errors": int(errors_match.group(1)),
                    "rx_errors": int(errors_match.group(2)),
                }

            status_list.append(stats)

        except Exception as e:
            logger.error(f"Failed to get status for CAN interface {iface_name}: {e}")
            status_list.append(
                CANInterfaceStats(interface_name=iface_name, is_up=False, state="UNKNOWN")
            )

    # Adjusted logging for clarity when status_list might be empty due to errors vs. no config
    if not status_list and interfaces_config:  # interfaces_config is not empty, but status_list is
        logger.warning(
            "CAN status endpoint: No interface status could be retrieved, "
            "though interfaces are configured. Check 'ip' command availability "
            "and interface states."
        )
        # Consider raising an error if no statuses could be retrieved despite configuration
        # raise HTTPException(
        #     status_code=500,
        #     detail="Could not retrieve CAN interface status for configured channels."
        # )
    # The case for not interfaces_config is handled at the beginning of the function now.

    return status_list


@api_router_can.get("/queue", response_model=Dict[str, Any])
async def get_queue_status():
    """
    Return the current status of the CAN transmit queue.
    """
    return {"length": can_tx_queue.qsize(), "maxsize": can_tx_queue.maxsize or "unbounded"}
