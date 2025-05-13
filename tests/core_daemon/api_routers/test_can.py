"""
Tests for the CAN API router in `core_daemon.api_routers.can`.

This module includes tests for:
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

# Use the correct import for the CAN interface function
from core_daemon.api_routers.can import get_can_interfaces_pyroute2 as get_can_interfaces
from core_daemon.can_manager import can_tx_queue


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
@patch("shutil.which")  # Add patch for shutil.which
async def test_get_can_interfaces_success_multiple(mock_shutil_which, mock_subprocess_shell):
    """Tests successful retrieval of multiple CAN interfaces."""

    # Configure shutil.which mocks
    def shutil_which_side_effect(cmd):
        if cmd == "ip":
            return "/mock/path/to/ip"
        if cmd == "awk":
            return "/mock/path/to/awk"
        return None

    mock_shutil_which.side_effect = shutil_which_side_effect

    # Mock the subprocess call
    process_mock = MagicMock()
    process_mock.communicate.return_value = (b"can0\ncan1\n", b"")
    process_mock.returncode = 0
    mock_subprocess_shell.return_value = process_mock

    interfaces = await get_can_interfaces()
    assert interfaces == ["can0", "can1"]
    # Command should now use the paths from shutil.which
    expected_command = (
        "/mock/path/to/ip -o link show type can " "| /mock/path/to/awk -F': ' '{print $2}'"
    )
    mock_subprocess_shell.assert_called_once_with(
        expected_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # Verify shutil.which was called for ip and awk
    mock_shutil_which.assert_any_call("ip")
    mock_shutil_which.assert_any_call("awk")


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
@patch("shutil.which")
async def test_get_can_interfaces_success_single(mock_shutil_which, mock_subprocess_shell):
    """Tests successful retrieval of a single CAN interface."""

    def shutil_which_side_effect(cmd):
        if cmd == "ip":
            return "/mock/path/to/ip"
        if cmd == "awk":
            return "/mock/path/to/awk"
        return None

    mock_shutil_which.side_effect = shutil_which_side_effect

    process_mock = MagicMock()
    process_mock.communicate.return_value = (b"can0\n", b"")  # Note the trailing newline
    process_mock.returncode = 0
    mock_subprocess_shell.return_value = process_mock

    interfaces = await get_can_interfaces()
    assert interfaces == ["can0"]
    expected_command = (
        "/mock/path/to/ip -o link show type can " "| /mock/path/to/awk -F': ' '{print $2}'"
    )
    mock_subprocess_shell.assert_called_once_with(
        expected_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
@patch("shutil.which")
async def test_get_can_interfaces_no_interfaces(mock_shutil_which, mock_subprocess_shell):
    """Tests retrieval when no CAN interfaces are found."""

    def shutil_which_side_effect(cmd):
        if cmd == "ip":
            return "/mock/path/to/ip"
        if cmd == "awk":
            return "/mock/path/to/awk"
        return None

    mock_shutil_which.side_effect = shutil_which_side_effect

    process_mock = MagicMock()
    process_mock.communicate.return_value = (b"", b"")  # Empty output
    process_mock.returncode = 0
    mock_subprocess_shell.return_value = process_mock

    interfaces = await get_can_interfaces()
    assert interfaces == []
    expected_command = (
        "/mock/path/to/ip -o link show type can " "| /mock/path/to/awk -F': ' '{print $2}'"
    )
    mock_subprocess_shell.assert_called_once_with(
        expected_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
@patch("shutil.which")
async def test_get_can_interfaces_ip_not_found(mock_shutil_which, mock_subprocess_shell):
    """Tests behavior when 'ip' command is not found by shutil.which."""

    def shutil_which_side_effect(cmd):
        if cmd == "ip":
            return None  # ip not found
        if cmd == "awk":
            return "/mock/path/to/awk"
        return None

    mock_shutil_which.side_effect = shutil_which_side_effect

    interfaces = await get_can_interfaces()
    assert interfaces == []
    mock_subprocess_shell.assert_not_called()  # Subprocess should not be called if ip is missing


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
@patch("shutil.which")
async def test_get_can_interfaces_awk_not_found(mock_shutil_which, mock_subprocess_shell):
    """Tests behavior when 'awk' command is not found by shutil.which."""

    def shutil_which_side_effect(cmd):
        if cmd == "ip":
            return "/mock/path/to/ip"
        if cmd == "awk":
            return None  # awk not found
        return None

    mock_shutil_which.side_effect = shutil_which_side_effect

    interfaces = await get_can_interfaces()
    assert interfaces == []
    mock_subprocess_shell.assert_not_called()  # Subprocess should not be called if awk is missing


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
@patch("shutil.which")  # Already patched, but good for clarity
async def test_get_can_interfaces_command_error(mock_shutil_which, mock_subprocess_shell):
    """Tests behavior when the 'ip link show' command returns an error."""

    def shutil_which_side_effect(cmd):
        if cmd == "ip":
            return "/mock/path/to/ip"
        if cmd == "awk":
            return "/mock/path/to/awk"
        return None

    mock_shutil_which.side_effect = shutil_which_side_effect

    process_mock = MagicMock()
    process_mock.communicate.return_value = (b"", b"Error executing command")
    process_mock.returncode = 1
    mock_subprocess_shell.return_value = process_mock

    interfaces = await get_can_interfaces()
    assert interfaces == []


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell", side_effect=Exception("Subprocess failed"))
@patch("shutil.which")  # shutil.which might be called before the exception
async def test_get_can_interfaces_exception(mock_shutil_which, mock_subprocess_shell):
    """Tests behavior when an exception occurs during subprocess execution."""

    def shutil_which_side_effect(cmd):
        if cmd == "ip":
            return "/mock/path/to/ip"
        if cmd == "awk":
            return "/mock/path/to/awk"
        return None

    mock_shutil_which.side_effect = shutil_which_side_effect
    interfaces = await get_can_interfaces()
    assert interfaces == []


# --- FastAPI TestClient Setup ---
# app = FastAPI() # Replaced by conftest.py app for client fixture
# app.include_router(api_router_can) # Ensure api_router_can is on the main app

# client = TestClient(app) # Replaced by client fixture from conftest.py


def test_get_queue_status(client):  # Added client fixture
    """Tests the /queue endpoint for an empty CAN transmit queue."""
    # Test with an empty queue
    # To properly test this, we might need to mock can_tx_queue if it's not easily resettable

    initial_qsize = can_tx_queue.qsize()

    response = client.get("/api/can/queue")  # Ensure prefix
    assert response.status_code == 200
    data = response.json()
    assert data["length"] == initial_qsize  # Check against actual qsize
    # If can_tx_queue is a standard asyncio.Queue(), its maxsize is 0,
    # and the endpoint logic returns "unbounded".
    assert data["maxsize"] == ("unbounded" if can_tx_queue.maxsize == 0 else can_tx_queue.maxsize)


@pytest.mark.asyncio
async def test_get_queue_status_with_items(client):  # Added client fixture
    """Tests the /queue endpoint when the CAN transmit queue has items."""
    # Temporarily put items in the queue if possible, or mock qsize
    # This is tricky as the queue is global. A better approach might be to
    # patch can_tx_queue for the duration of this test.

    with patch.object(can_tx_queue, "qsize", return_value=5):
        response = client.get("/api/can/queue")  # Ensure prefix
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
