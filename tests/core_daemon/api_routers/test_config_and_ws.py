"""
Tests for the API router managing configuration and WebSocket interactions.

This module contains tests for the endpoints defined in
`core_daemon.api_routers.config_and_ws.py`, including:
- Health and readiness probes (`/healthz`, `/readyz`).
- Prometheus metrics endpoint (`/metrics`).
- Configuration file retrieval (device mapping, RVC spec).
- WebSocket connection handling.

Mocks are used for file system operations (`os.path.exists`, `open`),
application state (`app_state`), and Prometheus client functions.
FastAPI's TestClient is used for endpoint testing.
"""

from unittest.mock import MagicMock, mock_open, patch

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from core_daemon.api_routers.config_and_ws import api_router_config_ws

# Setup FastAPI app with the router for testing
app = FastAPI()
app.include_router(api_router_config_ws)
client = TestClient(app)

# --- Health and Readiness Probes ---


def test_healthz():
    """Tests the /healthz liveness probe."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("core_daemon.api_routers.config_and_ws.app_state.state")
def test_readyz_when_ready(mock_app_state_state):
    """Tests the /readyz readiness probe when the application is ready."""
    mock_app_state_state.__len__.return_value = 1  # Simulate some entities exist
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "entities": 1}


@patch("core_daemon.api_routers.config_and_ws.app_state.state")
def test_readyz_when_not_ready(mock_app_state_state):
    """Tests the /readyz readiness probe when the application is not ready."""
    mock_app_state_state.__len__.return_value = 0  # Simulate no entities yet
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "pending", "entities": 0}


# --- Metrics Endpoint ---


@patch("core_daemon.api_routers.config_and_ws.generate_latest")
def test_metrics(mock_generate_latest):
    """Tests the /metrics Prometheus endpoint."""
    mock_metrics_data = b"# HELP my_metric Test metric\n# TYPE my_metric counter\nmy_metric 123\n"
    mock_generate_latest.return_value = mock_metrics_data

    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.content == mock_metrics_data
    # Shortened line E501
    expected_content_type = "text/plain; version=0.0.4; charset=utf-8"
    assert response.headers["content-type"] == expected_content_type
    mock_generate_latest.assert_called_once()


# --- Configuration File Endpoints ---

# Mock paths used by the router module. We patch these at the module level where they are imported.
# The router uses `actual_spec_path_for_ui` and `actual_map_path_for_ui` which are derived from
# `get_actual_paths`. It also uses `ACTUAL_SPEC_PATH` and `ACTUAL_MAP_PATH` directly imported from
# `core_daemon.config`.


@pytest.fixture(autouse=True)
def mock_config_paths():
    """Fixture to mock configuration file paths used by the API router."""
    # These paths are used by the endpoints directly or via get_actual_paths
    with patch(
        "core_daemon.api_routers.config_and_ws.actual_spec_path_for_ui", "/mock/spec_for_ui.json"
    ), patch(
        "core_daemon.api_routers.config_and_ws.actual_map_path_for_ui", "/mock/map_for_ui.yml"
    ), patch(
        "core_daemon.config.ACTUAL_SPEC_PATH", "/mock/actual_spec.json"
    ), patch(
        "core_daemon.config.ACTUAL_MAP_PATH", "/mock/actual_map.yml"
    ):
        yield


@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_get_device_mapping_config_content_api_success(mock_file_open, mock_exists):
    """Tests successful retrieval of device mapping content via API."""
    mock_exists.return_value = True
    mock_file_open.return_value.read.return_value = "device_mapping_content"

    response = client.get("/config/device_mapping")
    assert response.status_code == 200
    assert response.text == "device_mapping_content"
    mock_exists.assert_called_once_with("/mock/map_for_ui.yml")
    mock_file_open.assert_called_once_with("/mock/map_for_ui.yml", "r")


@patch("os.path.exists")
def test_get_device_mapping_config_content_api_not_found(mock_exists):
    """Tests API behavior when device mapping file is not found."""
    mock_exists.return_value = False
    response = client.get("/config/device_mapping")
    assert response.status_code == 404
    assert response.json() == {"detail": "Device mapping file not found."}


@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_get_device_mapping_config_content_api_read_error(mock_file_open, mock_exists):
    """Tests API behavior when reading device mapping file fails."""
    mock_exists.return_value = True
    mock_file_open.side_effect = Exception("Read error")
    response = client.get("/config/device_mapping")
    assert response.status_code == 500
    assert response.json() == {"detail": "Error reading device mapping file: Read error"}


@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_get_rvc_spec_details_success(mock_file_open, mock_exists):
    """Tests successful retrieval of RVC spec details."""
    mock_exists.return_value = True
    mock_file_open.return_value.read.return_value = '{"version": "1.0", "spec_document": "url"}'
    response = client.get("/config/rvc_spec_details")
    assert response.status_code == 200
    assert response.json() == {"version": "1.0", "spec_document": "url"}
    mock_exists.assert_called_once_with("/mock/spec_for_ui.json")
    mock_file_open.assert_called_once_with("/mock/spec_for_ui.json", "r")


@patch("os.path.exists")
def test_get_rvc_spec_details_not_found(mock_exists):
    """Tests API behavior when RVC spec file is not found for details endpoint."""
    mock_exists.return_value = False
    response = client.get("/config/rvc_spec_details")
    assert response.status_code == 404
    # Shortened line E501
    expected_detail = {"detail": "RVC spec file not found at /mock/spec_for_ui.json"}
    assert response.json() == expected_detail


@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_get_rvc_spec_details_decode_error(mock_file_open, mock_exists):
    """Tests API behavior when RVC spec file decoding fails for details endpoint."""
    mock_exists.return_value = True
    mock_file_open.return_value.read.return_value = "invalid_json"
    response = client.get("/config/rvc_spec_details")
    assert response.status_code == 500
    assert response.json() == {"detail": "Error decoding RVC spec file."}


@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_get_rvc_spec_metadata_success(mock_file_open, mock_exists):
    """Tests successful retrieval of RVC spec metadata."""
    mock_exists.return_value = True
    mock_file_open.return_value.read.return_value = '{"version": "2.0", "spec_document": "new_url"}'
    response = client.get("/config/rvc_spec_metadata")
    assert response.status_code == 200
    assert response.json() == {"version": "2.0", "spec_document": "new_url"}


# Similar error tests for rvc_spec_metadata as for rvc_spec_details (not found,
# decode error) ... (can be added if granular testing for this specific endpoint
# is needed beyond rvc_spec_details)


@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_get_rvc_spec_config_content_api_success(mock_file_open, mock_exists):
    """Tests successful retrieval of RVC spec content via API."""
    mock_exists.return_value = True
    mock_file_open.return_value.read.return_value = "spec_content"
    response = client.get("/config/rvc_spec")
    assert response.status_code == 200
    assert response.text == "spec_content"


# Similar error tests for rvc_spec_config_content_api (not found, read error)
# ...


# Tests for /config/spec and /config/mapping (FileResponse)
@patch("os.path.exists")
@patch("core_daemon.api_routers.config_and_ws.FileResponse")  # Patch FileResponse
def test_get_rvc_spec_file_contents_success(MockFileResponse, mock_exists):
    """Tests successful retrieval of RVC spec file contents using FileResponse."""
    mock_exists.return_value = True
    # Simulate FileResponse constructor and how it might be used or what it returns
    # For a TestClient, the actual file sending is handled, we just need to ensure
    # FileResponse is called.
    MockFileResponse.return_value = MagicMock(
        spec=Response, status_code=200, media_type="text/plain"
    )

    response = client.get("/config/spec")
    assert response.status_code == 200  # This will be the status_code of the mocked FileResponse
    mock_exists.assert_called_once_with("/mock/actual_spec.json")
    # Shortened line E501
    MockFileResponse.assert_called_once_with("/mock/actual_spec.json", media_type="text/plain")


@patch("os.path.exists")
def test_get_rvc_spec_file_contents_not_found(mock_exists):
    """Tests API behavior when RVC spec file is not found for FileResponse endpoint."""
    mock_exists.return_value = False
    response = client.get("/config/spec")
    assert response.status_code == 404
    assert response.json() == {"detail": "RVC Spec file not found."}


@patch("os.path.exists")
@patch("core_daemon.api_routers.config_and_ws.FileResponse")
def test_get_device_mapping_file_contents_success(MockFileResponse, mock_exists):
    """Tests successful retrieval of device mapping file contents using FileResponse."""
    mock_exists.return_value = True
    MockFileResponse.return_value = MagicMock(
        spec=Response, status_code=200, media_type="text/plain"
    )

    response = client.get("/config/mapping")
    assert response.status_code == 200
    mock_exists.assert_called_once_with("/mock/actual_map.yml")
    MockFileResponse.assert_called_once_with("/mock/actual_map.yml", media_type="text/plain")


@patch("os.path.exists")
def test_get_device_mapping_file_contents_not_found(mock_exists):
    """Tests API behavior when device mapping file is not found for FileResponse endpoint."""
    mock_exists.return_value = False
    response = client.get("/config/mapping")
    assert response.status_code == 404
    assert response.json() == {"detail": "Device mapping file not found."}


# --- WebSocket Endpoints (Basic Tests) ---
# These tests will verify that the WebSocket routes are defined and call the respective handlers.
# Full WebSocket interaction testing is more complex and might require a WebSocket client library.


@patch("core_daemon.api_routers.config_and_ws.websocket_endpoint", new_callable=MagicMock)
async def test_serve_websocket_endpoint(mock_ws_endpoint):
    """Tests that the /ws WebSocket endpoint is defined and calls the correct handler."""
    # FastAPI's TestClient provides a way to test WebSockets
    with client.websocket_connect("/ws") as _websocket:  # noqa: F841
        # We are not sending/receiving data here, just checking connection and handler call
        pass  # Connection itself is the test for the route
    mock_ws_endpoint.assert_called_once()  # Check if our handler was called


@patch("core_daemon.api_routers.config_and_ws.websocket_logs_endpoint", new_callable=MagicMock)
async def test_serve_websocket_logs_endpoint(mock_ws_logs_endpoint):
    """Tests that the /ws/logs WebSocket endpoint is defined and calls the correct handler."""
    with client.websocket_connect("/ws/logs") as _websocket:  # noqa: F841
        pass
    mock_ws_logs_endpoint.assert_called_once()
