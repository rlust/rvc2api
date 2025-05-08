"""
Defines FastAPI APIRouter for CAN bus related operations.

This module includes routes to get the status of CAN interfaces,
check the CAN transmit queue, and potentially other CAN-specific actions.
"""

import asyncio
import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

# Assuming can_tx_queue is in core_daemon.can_manager
from core_daemon.can_manager import can_tx_queue

# Assuming CANInterfaceStats model is in core_daemon.models
from core_daemon.models import AllCANStats, CANInterfaceStats

logger = logging.getLogger(__name__)

api_router_can = APIRouter()  # FastAPI router for CAN-related endpoints


def parse_ip_link_show(output: str, interface_name: str) -> Optional[CANInterfaceStats]:
    """
    Parses the output of `ip -details -statistics link show <interface_name>`
    for a CAN interface.

    Args:
        output: The string output from the `ip` command.
        interface_name: The name of the interface (e.g., "can0").

    Returns:
        A CANInterfaceStats object populated with the parsed data,
        or None if essential information couldn't be parsed (though it
        tries to return a partial object).
    """
    stats = CANInterfaceStats(name=interface_name)
    stats.raw_details = output  # Store raw output for debugging or future use

    # Overall interface state line (e.g., state UP, state DOWN)
    match = re.search(rf"^\d+: {re.escape(interface_name)}: .* state (\S+)", output, re.MULTILINE)
    if match:
        stats.state = match.group(1)  # This is the general link state, CAN state is more specific

    # link/can line
    match = re.search(r"link/can\s+promiscuity\s+(\d+)\s+allmulti\s+(\d+)", output)
    if match:
        stats.promiscuity = int(match.group(1))
        stats.allmulti = int(match.group(2))

    # CAN specific state line: "can state ERROR-PASSIVE restart-ms 0"
    can_state_match = re.search(r"can state ([\w-]+)(?: restart-ms (\d+))?", output)
    if can_state_match:
        stats.state = can_state_match.group(1)  # Override general state with specific CAN state
        if can_state_match.group(2):
            stats.restart_ms = int(can_state_match.group(2))

    # Bitrate and sample-point: "bitrate 250000 sample-point 0.875"
    bitrate_match = re.search(r"bitrate (\d+) sample-point (\S+)", output)
    if bitrate_match:
        stats.bitrate = int(bitrate_match.group(1))
        try:
            stats.sample_point = float(bitrate_match.group(2))
        except ValueError:
            logger.warning(
                f"Could not parse sample-point for {interface_name}: {bitrate_match.group(2)}"
            )

    # Timing parameters: "tq 250 prop-seg 6 phase-seg1 7 phase-seg2 2 sjw 1 brp 2"
    timing_match = re.search(
        r"tq (\d+) prop-seg (\d+) phase-seg1 (\d+) phase-seg2 (\d+) sjw (\d+) brp (\d+)", output
    )
    if timing_match:
        stats.tq = int(timing_match.group(1))
        stats.prop_seg = int(timing_match.group(2))
        stats.phase_seg1 = int(timing_match.group(3))
        stats.phase_seg2 = int(timing_match.group(4))
        stats.sjw = int(timing_match.group(5))
        stats.brp = int(timing_match.group(6))

    # Clock frequency: "clock 8000000"
    clock_match = re.search(r"clock (\d+)", output)
    if clock_match:
        stats.clock_freq = int(clock_match.group(1))

    # Parent bus/dev: "parentbus spi parentdev spi0.1"
    parent_match = re.search(r"parentbus (\S+) parentdev (\S+)", output)
    if parent_match:
        stats.parentbus = parent_match.group(1)
        stats.parentdev = parent_match.group(2)

    # Statistics lines (RX and TX)
    # RX: bytes  packets  errors  dropped overrun mcast
    # 12345      67890    12      3       4       0
    rx_stats_match = re.search(
        r"RX: bytes\s+packets\s+errors\s+dropped\s+overrun\s+mcast\s*\n"
        r"\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        output,
        re.MULTILINE,
    )
    if rx_stats_match:
        stats.rx_bytes = int(rx_stats_match.group(1))
        stats.rx_packets = int(rx_stats_match.group(2))
        stats.rx_errors = int(rx_stats_match.group(3))
        # Potentially add dropped, overrun if needed in model

    # TX: bytes  packets  errors  dropped carrier collsns
    # 12345      67890    12      3       4       0
    tx_stats_match = re.search(
        r"TX: bytes\s+packets\s+errors\s+dropped\s+carrier\s+collsns\s*\n"
        r"\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        output,
        re.MULTILINE,
    )
    if tx_stats_match:
        stats.tx_bytes = int(tx_stats_match.group(1))
        stats.tx_packets = int(tx_stats_match.group(2))
        stats.tx_errors = int(tx_stats_match.group(3))
        # Potentially add dropped, carrier, collsns if needed in model

    # More specific error counters from ip -s -d link show canX
    # Example: "bus-error 0 error-warning 0 error-passive 0 bus-off 0"
    # Note: These might not always be present or might be on a different line.
    # This regex is a bit more flexible.
    detailed_errors_match = re.search(
        r"(?:bus-error\s+(\d+))?\s*"
        r"(?:error-warning\s+(\d+))?\s*"
        r"(?:error-passive\s+(\d+))?\s*"
        r"(?:bus-off\s+(\d+))?",
        output,
    )
    if detailed_errors_match:
        if detailed_errors_match.group(1):
            stats.bus_errors = int(detailed_errors_match.group(1))
        if detailed_errors_match.group(2):
            stats.error_warning = int(detailed_errors_match.group(2))
        if detailed_errors_match.group(3):
            stats.error_passive = int(detailed_errors_match.group(3))
        if detailed_errors_match.group(4):
            stats.bus_off = int(detailed_errors_match.group(4))

    # If 'restarts' is mentioned separately, e.g. from
    # `can state ERROR-PASSIVE restart-ms 0 restarts 5`
    # The current `can state` regex handles restart-ms. If `restarts` (count) is separate:
    restarts_count_match = re.search(r"restarts (\d+)", output)
    if restarts_count_match:
        stats.restarts = int(restarts_count_match.group(1))

    # Fallback for bus_errors if not found in detailed_errors_match but present
    # in statistics section
    # This is common if `ip -s link show` is used without `-d` for some counters
    if stats.bus_errors is None:
        bus_error_simple_match = re.search(r"bus-error\s+(\d+)", output)
        if bus_error_simple_match:
            stats.bus_errors = int(bus_error_simple_match.group(1))

    return stats


async def get_can_interfaces() -> list[str]:
    """
    Lists available CAN interfaces by checking 'ip link show type can'.

    Uses `ip -o link show type can | awk -F': ' '{print $2}'` to get a list
    of CAN interface names.

    Returns:
        A list of CAN interface names (e.g., ["can0", "can1"]), or an empty
        list if none are found or an error occurs.
    """
    try:
        proc = await asyncio.create_subprocess_shell(
            "/run/current-system/sw/bin/ip -o link show type can \
            | /run/current-system/sw/bin/awk -F': ' '{print $2}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            interfaces = stdout.decode().strip().split("\n")
            return [iface for iface in interfaces if iface]  # Filter out empty strings
        else:
            logger.error(f"Error listing CAN interfaces: {stderr.decode()}")
            return []
    except Exception as e:
        logger.error(f"Exception listing CAN interfaces: {e}")
        return []


@api_router_can.get("/can/status", response_model=AllCANStats)
async def get_can_status():
    """
    Retrieves detailed status for all CAN interfaces.

    This endpoint iterates through all detected CAN interfaces and fetches
    detailed statistics for each using the `ip -details -statistics link show <interface>`
    command. The output of this command is then parsed to populate the
    `CANInterfaceStats` model for each interface.

    Returns:
        An `AllCANStats` object containing a dictionary where keys are
        interface names and values are `CANInterfaceStats` objects.
        Returns an empty dictionary if no interfaces are found or if
        there's an error in fetching their statuses.
    """
    interfaces_data: Dict[str, CANInterfaceStats] = {}
    interface_names = await get_can_interfaces()

    if not interface_names:
        # Return empty if no interfaces found, or error occurred.
        # Frontend should handle this by showing "No CAN interfaces found".
        return AllCANStats(interfaces={})

    for iface_name in interface_names:
        try:
            # Using -details -statistics for the most comprehensive output
            command = f"/run/current-system/sw/bin/ip -details -statistics link show {iface_name}"
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                output_str = stdout.decode()
                parsed_stats = parse_ip_link_show(output_str, iface_name)
                if parsed_stats:
                    interfaces_data[iface_name] = parsed_stats
                else:
                    logger.warning(f"Could not parse details for {iface_name}")
                    # Add a basic entry even if parsing fails partially
                    interfaces_data[iface_name] = CANInterfaceStats(
                        name=iface_name, state="Unknown/ParseError"
                    )
            else:
                error_msg = stderr.decode()
                logger.error(f"Error getting status for {iface_name}: {error_msg}")
                interfaces_data[iface_name] = CANInterfaceStats(
                    name=iface_name, state="Error/NotAvailable"
                )
        except Exception as e:
            logger.exception(f"Exception processing interface {iface_name}: {e}")
            interfaces_data[iface_name] = CANInterfaceStats(name=iface_name, state="Exception")

    if not interfaces_data and interface_names:  # Should not happen if logic above is correct
        raise HTTPException(
            status_code=404, detail="CAN interfaces found but failed to retrieve status for all."
        )

    return AllCANStats(interfaces=interfaces_data)


@api_router_can.get("/queue", response_model=Dict[str, Any])
async def get_queue_status():
    """
    Return the current status of the CAN transmit queue.

    Provides the current number of items in the `can_tx_queue` and its
    maximum configured size.

    Returns:
        A dictionary with "length" (current queue size) and "maxsize"
        (maximum queue size, or "unbounded").
    """
    return {"length": can_tx_queue.qsize(), "maxsize": can_tx_queue.maxsize or "unbounded"}
