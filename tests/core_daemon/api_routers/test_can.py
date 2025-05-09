"""
Tests for the CAN API router in `core_daemon.api_routers.can`.

This module includes tests for:
- Parsing output from `ip -details -statistics link show <interface>`.
- Retrieving available CAN interfaces.
- The `/can/status` API endpoint.
- The `/queue` API endpoint (for CAN transmission queue status).

Mocks are used extensively to simulate subprocess calls (`ip` command) and
to isolate the logic of parsing and API endpoint handling. FastAPI's TestClient
is used for endpoint testing.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core_daemon.api_routers.can import api_router_can, get_can_interfaces, parse_ip_link_show
from core_daemon.can_manager import can_tx_queue  # Assuming this is an asyncio.Queue
from core_daemon.models import CANInterfaceStats

# Sample outputs from 'ip -details -statistics link show <interface>'
SAMPLE_IP_LINK_SHOW_CAN0_UP = (
    "\n"
    "3: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP mode DEFAULT group "
    "default qlen 10\n"
    "    link/can  promiscuity 0 allmulti 0\n"
    "    can state ERROR-ACTIVE restart-ms 0\n"
    "    bitrate 250000 sample-point 0.875\n"
    "    tq 250 prop-seg 6 phase-seg1 7 phase-seg2 2 sjw 1\n"
    "    mcp251xfd: tdc-mode TDC_AUTO tdc-offset 31 tdc-filter 31\n"
    "    clock 8000000 parentbus spi parentdev spi0.0\n"
    "    RX: bytes  packets  errors  dropped overrun mcast\n"
    "    12345      67890    12      3       4       0\n"
    "    TX: bytes  packets  errors  dropped carrier collsns\n"
    "    54321      98760    21      5       6       0\n"
    "    bus-error 0 error-warning 1 error-passive 2 bus-off 3 restarts 4\n"
)

SAMPLE_IP_LINK_SHOW_CAN1_DOWN = """
4: can1: <NOARP,DOWN,ECHO> mtu 16 qdisc noop state DOWN mode DEFAULT group default qlen 10
    link/can  promiscuity 0 allmulti 0
    can state STOPPED
    clock 8000000
    RX: bytes  packets  errors  dropped overrun mcast
    0          0        0       0       0       0
    TX: bytes  packets  errors  dropped carrier collsns
    0          0        0       0       0       0
"""

SAMPLE_IP_LINK_SHOW_CAN2_NO_DETAILS = (
    "\n"
    "5: can2: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP mode DEFAULT group "
    "default qlen 10\n"
    "    link/can\n"
    "    can state ERROR-ACTIVE\n"
    "    bitrate 500000 sample-point 0.750\n"
    "    RX: bytes  packets  errors  dropped overrun mcast\n"
    "    100        10       0       0       0       0\n"
    "    TX: bytes  packets  errors  dropped carrier collsns\n"
    "    200        20       0       0       0       0\n"
)


def test_parse_ip_link_show_can0_up():
    """Tests parsing of 'ip link show' output for an UP CAN interface with full details."""
    stats = parse_ip_link_show(SAMPLE_IP_LINK_SHOW_CAN0_UP, "can0")
    assert stats is not None
    assert stats.name == "can0"
    # The overall link state is UP, but CAN state is ERROR-ACTIVE
    assert stats.state == "ERROR-ACTIVE"
    assert stats.promiscuity == 0
    assert stats.allmulti == 0
    assert stats.restart_ms == 0
    assert stats.bitrate == 250000
    assert stats.sample_point == 0.875
    assert stats.tq == 250
    assert stats.prop_seg == 6
    assert stats.phase_seg1 == 7
    assert stats.phase_seg2 == 2
    assert stats.sjw == 1
    assert stats.clock_freq == 8000000
    assert stats.parentbus == "spi"
    assert stats.parentdev == "spi0.0"
    assert stats.rx_bytes == 12345
    assert stats.rx_packets == 67890
    assert stats.rx_errors == 12
    assert stats.tx_bytes == 54321
    assert stats.tx_packets == 98760
    assert stats.tx_errors == 21
    assert stats.bus_errors == 0
    assert stats.error_warning == 1
    assert stats.error_passive == 2
    assert stats.bus_off == 3
    assert stats.restarts == 4
    assert stats.raw_details == SAMPLE_IP_LINK_SHOW_CAN0_UP


def test_parse_ip_link_show_can1_down():
    """Tests parsing of 'ip link show' output for a DOWN CAN interface."""
    stats = parse_ip_link_show(SAMPLE_IP_LINK_SHOW_CAN1_DOWN, "can1")
    assert stats is not None
    assert stats.name == "can1"
    assert stats.state == "STOPPED"  # CAN state is STOPPED
    assert stats.bitrate is None  # No bitrate info when down
    assert stats.clock_freq == 8000000
    assert stats.rx_packets == 0
    assert stats.tx_packets == 0
    assert stats.raw_details == SAMPLE_IP_LINK_SHOW_CAN1_DOWN


def test_parse_ip_link_show_can2_no_details():
    """Tests parsing of 'ip link show' output for an UP CAN interface with some details missing."""
    stats = parse_ip_link_show(SAMPLE_IP_LINK_SHOW_CAN2_NO_DETAILS, "can2")
    assert stats is not None
    assert stats.name == "can2"
    assert stats.state == "ERROR-ACTIVE"
    assert stats.bitrate == 500000
    assert stats.sample_point == 0.750
    assert stats.tq is None  # Missing in this sample
    assert stats.clock_freq is None  # Missing
    assert stats.rx_bytes == 100
    assert stats.tx_bytes == 200
    assert stats.bus_errors is None  # Missing
    assert stats.raw_details == SAMPLE_IP_LINK_SHOW_CAN2_NO_DETAILS


def test_parse_ip_link_show_empty_output():
    """Tests parsing of empty 'ip link show' output."""
    stats = parse_ip_link_show("", "can0")
    assert stats is not None  # Function creates a base CANInterfaceStats object
    assert stats.name == "can0"
    assert stats.state is None  # No info to parse


def test_parse_ip_link_show_minimal_output():
    """
    Tests parsing of minimal 'ip link show' output for an UP interface.
    """
    output = (
        "2: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP "
        "mode DEFAULT group default qlen 10\\n    link/can"
    )
    stats = parse_ip_link_show(output, "can0")
    assert stats is not None
    assert stats.name == "can0"
    # The general link state is UP, but no specific CAN state line
    # The current parsing logic might pick up the general 'UP' or default to
    # None if 'can state' line is missing.
    # Based on current parse_ip_link_show, it will be 'UP' from the first line,
    # then overridden if 'can state' is found.
    # If 'can state' is not found, it remains 'UP'.
    # Let's assume for minimal output, if 'can state' is missing,
    # it might be better to be None or reflect the general link state.
    # The model has state as Optional[str], so None is valid.
    # The function first searches for `^\d+: {re.escape(interface_name)}: .* state (\S+)`
    # then `can state ([\w-]+)` which overrides. If the second is not found,
    # the first match remains.
    assert stats.state == "UP"  # From the first line, as 'can state' is missing.


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
async def test_get_can_interfaces_success_multiple(mock_subprocess_shell):
    """Tests successful retrieval of multiple CAN interfaces."""
    # Mock the subprocess call
    process_mock = MagicMock()
    process_mock.communicate.return_value = (b"can0\ncan1\n", b"")
    process_mock.returncode = 0
    mock_subprocess_shell.return_value = process_mock

    interfaces = await get_can_interfaces()
    assert interfaces == ["can0", "can1"]
    expected_command = (
        "/run/current-system/sw/bin/ip -o link show type can "
        "| /run/current-system/sw/bin/awk -F': ' '{print $2}'"
    )
    mock_subprocess_shell.assert_called_once_with(
        expected_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
async def test_get_can_interfaces_success_single(mock_subprocess_shell):
    """Tests successful retrieval of a single CAN interface."""
    process_mock = MagicMock()
    process_mock.communicate.return_value = (b"can0\n", b"")  # Note the trailing newline
    process_mock.returncode = 0
    mock_subprocess_shell.return_value = process_mock

    interfaces = await get_can_interfaces()
    assert interfaces == ["can0"]
    expected_command = (
        "/run/current-system/sw/bin/ip -o link show type can "
        "| /run/current-system/sw/bin/awk -F': ' '{print $2}'"
    )
    mock_subprocess_shell.assert_called_once_with(
        expected_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
async def test_get_can_interfaces_no_interfaces(mock_subprocess_shell):
    """Tests retrieval when no CAN interfaces are found."""
    process_mock = MagicMock()
    process_mock.communicate.return_value = (b"", b"")  # Empty output
    process_mock.returncode = 0
    mock_subprocess_shell.return_value = process_mock

    interfaces = await get_can_interfaces()
    assert interfaces == []
    expected_command = (
        "/run/current-system/sw/bin/ip -o link show type can "
        "| /run/current-system/sw/bin/awk -F': ' '{print $2}'"
    )
    mock_subprocess_shell.assert_called_once_with(
        expected_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
async def test_get_can_interfaces_command_error(mock_subprocess_shell):
    """Tests behavior when the 'ip link show' command returns an error."""
    process_mock = MagicMock()
    process_mock.communicate.return_value = (b"", b"Error executing command")
    process_mock.returncode = 1
    mock_subprocess_shell.return_value = process_mock

    interfaces = await get_can_interfaces()
    assert interfaces == []


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell", side_effect=Exception("Subprocess failed"))
async def test_get_can_interfaces_exception(mock_subprocess_shell):
    """Tests behavior when an exception occurs during subprocess execution."""
    interfaces = await get_can_interfaces()
    assert interfaces == []


# --- FastAPI TestClient Setup ---
app = FastAPI()
app.include_router(api_router_can)

client = TestClient(app)


@patch("core_daemon.api_routers.can.get_can_interfaces")
@patch("core_daemon.api_routers.can.parse_ip_link_show")
@patch("asyncio.create_subprocess_shell")  # Mock shell call in endpoint
def test_get_can_status_success(mock_subprocess_shell_ip, mock_parse_ip, mock_get_interfaces):
    """Tests the /can/status endpoint for successful retrieval of multiple interface statuses."""
    mock_get_interfaces.return_value = ["can0", "can1"]

    # Mock behavior for parse_ip_link_show or the subprocess call it makes
    # Option 1: Mock parse_ip_link_show directly
    def mock_parse_side_effect(output_str, iface_name):
        if iface_name == "can0":
            return CANInterfaceStats(
                name="can0", state="UP", bitrate=250000, raw_details=output_str
            )
        if iface_name == "can1":
            return CANInterfaceStats(name="can1", state="DOWN", raw_details=output_str)
        return None

    mock_parse_ip.side_effect = mock_parse_side_effect

    # Mock the subprocess call that the endpoint itself
    # makes to get the raw string for parse_ip_link_show
    async def mock_communicate_can0():
        return (SAMPLE_IP_LINK_SHOW_CAN0_UP.encode(), b"")

    async def mock_communicate_can1():
        return (SAMPLE_IP_LINK_SHOW_CAN1_DOWN.encode(), b"")

    process_mock_can0 = MagicMock()
    process_mock_can0.communicate = MagicMock(side_effect=mock_communicate_can0)
    process_mock_can0.returncode = 0

    process_mock_can1 = MagicMock()
    process_mock_can1.communicate = MagicMock(side_effect=mock_communicate_can1)
    process_mock_can1.returncode = 0

    def mock_shell_side_effect(command, stdout, stderr):
        if "can0" in command:
            return process_mock_can0
        elif "can1" in command:
            return process_mock_can1
        raise ValueError("Unexpected command in mock_shell_side_effect")

    mock_subprocess_shell_ip.side_effect = mock_shell_side_effect

    response = client.get("/can/status")
    assert response.status_code == 200
    data = response.json()
    assert "interfaces" in data
    assert "can0" in data["interfaces"]
    assert "can1" in data["interfaces"]
    assert data["interfaces"]["can0"]["name"] == "can0"
    assert data["interfaces"]["can0"]["state"] == "UP"
    assert data["interfaces"]["can0"]["bitrate"] == 250000
    assert data["interfaces"]["can1"]["name"] == "can1"
    assert data["interfaces"]["can1"]["state"] == "DOWN"


@patch("core_daemon.api_routers.can.get_can_interfaces", return_value=["can0"])
@patch("asyncio.create_subprocess_shell")
def test_get_can_status_interface_error(mock_subprocess_shell, mock_get_interfaces):
    """Tests the /can/status endpoint when fetching details for an interface fails."""
    # Simulate error when getting details for can0
    process_mock_error = MagicMock()
    process_mock_error.communicate.return_value = (b"", b"ip command failed for can0")
    process_mock_error.returncode = 1
    mock_subprocess_shell.return_value = process_mock_error

    response = client.get("/can/status")
    assert (
        response.status_code == 200
    )  # Endpoint still returns 200 but with error state for interface
    data = response.json()
    assert "interfaces" in data
    assert "can0" in data["interfaces"]
    assert data["interfaces"]["can0"]["name"] == "can0"
    assert data["interfaces"]["can0"]["state"] == "Error/NotAvailable"


@patch("core_daemon.api_routers.can.get_can_interfaces", return_value=[])
def test_get_can_status_no_interfaces(mock_get_interfaces):
    """Tests the /can/status endpoint when no CAN interfaces are available."""
    response = client.get("/can/status")
    assert response.status_code == 200
    data = response.json()
    assert "interfaces" in data
    assert data["interfaces"] == {}


def test_get_queue_status():
    """Tests the /queue endpoint for an empty CAN transmit queue."""
    # Test with an empty queue
    # To properly test this, we might need to mock can_tx_queue if it's not easily resettable
    # For now, assume it's an asyncio.Queue and we can check its current state
    # If can_tx_queue is imported directly, we can patch it or its methods.

    initial_qsize = can_tx_queue.qsize()

    response = client.get("/queue")
    assert response.status_code == 200
    data = response.json()
    assert data["length"] == initial_qsize  # Check against actual qsize
    # If can_tx_queue is a standard asyncio.Queue(), its maxsize is 0,
    # and the endpoint logic returns "unbounded".
    assert data["maxsize"] == ("unbounded" if can_tx_queue.maxsize == 0 else can_tx_queue.maxsize)


@pytest.mark.asyncio
async def test_get_queue_status_with_items():
    """Tests the /queue endpoint when the CAN transmit queue has items."""
    # Temporarily put items in the queue if possible, or mock qsize
    # This is tricky as the queue is global. A better approach might be to
    # patch can_tx_queue for the duration of this test.

    with patch.object(can_tx_queue, "qsize", return_value=5):
        response = client.get("/queue")
        assert response.status_code == 200
        data = response.json()
        assert data["length"] == 5
        # If can_tx_queue is a standard asyncio.Queue(), its maxsize is 0,
        # and the endpoint logic returns "unbounded".
        assert data["maxsize"] == (
            "unbounded" if can_tx_queue.maxsize == 0 else can_tx_queue.maxsize
        )

    # Ensure queue is back to normal or original mock state after patch
    # If we actually put items, we'd need to get them.
    # For this example, patching qsize is cleaner for a unit test.
