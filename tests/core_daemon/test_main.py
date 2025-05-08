"""
Tests for the main FastAPI application setup and core functionalities in `core_daemon.main`.

This module includes tests for:
- The `main()` function and its call to `uvicorn.run`.
- FastAPI application instance (`app`) creation and configuration:
    - Mounting of static files and Jinja2 templates.
    - Inclusion of API routers.
    - Registration of custom exception handlers.
    - Execution of startup and shutdown event handlers.
- Specific endpoints like the root ("/") endpoint.
- Middleware integration (e.g., Prometheus metrics).

The tests extensively use mocking to isolate the `main.py` module from its
dependencies (like CAN hardware, actual file system operations, external services),
allowing for focused unit testing of its logic.
"""

import os
import unittest.mock  # Added import for unittest.mock
from unittest.mock import MagicMock, patch

from fastapi import Response  # Removed unused Request import
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient


# For testing the main() function that calls uvicorn.run
@patch.dict(
    os.environ, {"RVC2API_HOST": "127.0.0.1", "RVC2API_PORT": "9000", "RVC2API_LOG_LEVEL": "debug"}
)
@patch("uvicorn.run")
@patch("core_daemon.main.configure_logger")
@patch("core_daemon.main.get_actual_paths")
@patch("core_daemon.main.load_config_data")
@patch("core_daemon.main.initialize_app_from_config")
@patch("core_daemon.main.initialize_can_listeners")  # To prevent actual CAN setup
@patch("core_daemon.main.initialize_can_writer_task")  # To prevent actual CAN setup
@patch("core_daemon.main.setup_websocket_logging")  # To prevent actual WS logging setup
def test_main_function_calls_uvicorn(
    mock_initialize_app,
    mock_load_config,
    mock_get_paths,
    mock_configure_logger,
    mock_uvicorn_run,
):
    """
    Tests that the main() function correctly initializes the application
    and calls uvicorn.run with the expected app instance and configuration
    derived from environment variables.
    """
    # Import main function here to ensure patches are active
    from core_daemon.main import app as actual_app
    from core_daemon.main import main as main_function

    main_function()

    mock_configure_logger.assert_called_once()
    mock_get_paths.assert_called_once()
    mock_load_config.assert_called_once()
    mock_initialize_app.assert_called_once()

    # Uvicorn should be called with the app instance from main.py
    # and host, port, log_level from patched environment variables
    mock_uvicorn_run.assert_called_once()
    args, kwargs = mock_uvicorn_run.call_args
    assert args[0] == actual_app  # Check if the correct app instance is passed
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 9000
    assert kwargs["log_level"] == "debug"


# For testing FastAPI app setup, we need to import 'app' from main
# This requires careful patching of dependencies that run on module load or app creation.


@patch("os.path.isdir")
@patch("core_daemon.main.StaticFiles", spec=StaticFiles)  # Mock the class
@patch("core_daemon.main.Jinja2Templates", spec=Jinja2Templates)  # Mock the class
@patch("core_daemon.main.get_static_paths")
@patch("core_daemon.main.configure_logger")  # Prevent logging setup during import
@patch("core_daemon.main.get_actual_paths")  # Prevent path logic
@patch("core_daemon.main.load_config_data")  # Prevent data loading
@patch("core_daemon.main.initialize_app_from_config")  # Prevent app state init
@patch("core_daemon.main.initialize_can_listeners")
@patch("core_daemon.main.initialize_can_writer_task")
@patch("core_daemon.main.setup_websocket_logging")
def test_fastapi_app_setup_static_and_templates_mounted(
    mock_setup_ws_logging,
    mock_init_can_writer,
    mock_init_can_listeners,
    mock_initialize_app,
    mock_load_config,
    mock_get_paths,
    mock_configure_logger,
    mock_get_static_paths,
    MockJinja2Templates,
    MockStaticFiles,
    mock_os_path_isdir,
):
    """
    Tests that the FastAPI application correctly sets up static file serving
    and Jinja2 template rendering. It verifies that StaticFiles and Jinja2Templates
    are instantiated with the correct directory paths, and that these paths
    are obtained from get_static_paths.
    """
    # Define what get_static_paths will return for this test
    mock_get_static_paths.return_value = {
        "web_ui_dir": "/fake/web_ui",
        "static_dir": "/fake/static",
        "templates_dir": "/fake/templates",
    }
    # Simulate that directories exist
    mock_os_path_isdir.return_value = True

    # Import 'app' here, after patches are set up
    # Check if StaticFiles was mounted
    # The actual mounting is done via app.mount(), we check if StaticFiles
    # was instantiated correctly
    MockStaticFiles.assert_called_once_with(
        directory="/fake/static", follow_symlink=True
    )  # Shortened E501

    # Check if Jinja2Templates was instantiated
    MockJinja2Templates.assert_called_once_with(directory="/fake/templates")

    # Verify that app.mount was called for static files.
    # This requires inspecting the app's router or mount calls if possible,
    # or ensuring the StaticFiles instance created was used in a mount call.
    # FastAPI's TestClient doesn't easily expose mount points for direct assertion.
    # We'll rely on the instantiation check of StaticFiles and Jinja2Templates.


@patch("core_daemon.main.configure_logger")
@patch("core_daemon.main.get_actual_paths")
@patch("core_daemon.main.load_config_data")
@patch("core_daemon.main.initialize_app_from_config")
@patch("core_daemon.main.initialize_can_listeners")
@patch("core_daemon.main.initialize_can_writer_task")
@patch("core_daemon.main.setup_websocket_logging")
def test_api_routers_included(
    mock_setup_ws_logging,
    mock_init_can_writer,
    mock_init_can_listeners,
    mock_initialize_app,
    mock_load_config,
    mock_get_paths,
    mock_configure_logger,
):
    """
    Tests that all designated API routers (for CAN, config/WebSockets, entities)
    are correctly included in the main FastAPI application.
    It checks for the presence of known routes from each router.
    """
    from core_daemon.main import app

    # Check if routers are included. FastAPI stores routes in app.router.routes
    # We can check if the routes from our routers are present.
    # This is a bit of an internal check, but useful.
    # A simpler way is to use the TestClient to hit an endpoint from each router.
    # Test an endpoint from api_router_can (needs mocks for its dependencies if any are hit)
    # For now, just check if the router is in the app's list of routers
    # Note: FastAPI composes routers, so direct check of app.router.routes is complex.
    # A more robust check is to see if the app's routes contain routes defined by these routers.
    # Example: Check if a known path from one of the routers exists
    # This is more of an integration test style check for a unit test file.
    # For a unit test of main.py, it's more about *if* include_router was called.
    # We can mock app.include_router if we want to be very pure.
    # Let's assume for now that if the import works and app is created,
    # the include_router lines were executed. A more detailed test would involve
    # mocking app.include_router and asserting it was called with the correct routers and prefixes.
    # For this test, we'll just ensure the app has routes.
    assert len(app.router.routes) > 0

    # A more specific check could be to find a route by path template
    # e.g. any(route.path == "/api/can/interfaces" for route in app.routes)
    # This requires knowing specific paths from each router.

    # Check if the main app's routers list contains the imported routers
    # FastAPI's app.routes includes routes from mounted apps and included routers
    # We can check if the app's routes contain routes that belong to our specific routers

    # Get all route paths
    route_paths = [route.path for route in app.routes if hasattr(route, "path")]  # Shortened E501

    # Check for a known path from each router (assuming they have at
    # least one GET endpoint at their root)
    # These paths depend on the prefix used in app.include_router()
    assert "/api/can/interfaces" in route_paths  # From api_router_can
    assert "/api/healthz" in route_paths  # From api_router_config_ws
    assert "/api/entities" in route_paths  # From api_router_entities
    assert "/" in route_paths  # For the root endpoint


@patch("core_daemon.main.configure_logger")
@patch("core_daemon.main.get_actual_paths")
@patch("core_daemon.main.load_config_data")
@patch("core_daemon.main.initialize_app_from_config")
@patch("core_daemon.main.initialize_can_listeners")
@patch("core_daemon.main.initialize_can_writer_task")
@patch("core_daemon.main.setup_websocket_logging")
@patch("core_daemon.main.templates")  # Mock the template engine
def test_root_endpoint(
    mock_templates,
    mock_setup_ws_logging,
    mock_init_can_writer,
    mock_init_can_listeners,
    mock_initialize_app,
    mock_load_config,
    mock_get_paths,
    mock_configure_logger,
):
    """
    Tests the root ("/") endpoint, ensuring it returns a 200 OK status
    and the expected HTML content by successfully calling the template engine
    with 'index.html'.
    """
    from core_daemon.main import app

    client = TestClient(app)

    # Mock the TemplateResponse
    mock_templates.TemplateResponse = MagicMock(
        return_value=Response("<html></html>", media_type="text/html")
    )

    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    mock_templates.TemplateResponse.assert_called_once_with(
        "index.html", {"request": unittest.mock.ANY}
    )


# Test for the custom validation exception handler
@patch("core_daemon.main.configure_logger")
@patch("core_daemon.main.get_actual_paths")
@patch("core_daemon.main.load_config_data")
@patch("core_daemon.main.initialize_app_from_config")
@patch("core_daemon.main.initialize_can_listeners")
@patch("core_daemon.main.initialize_can_writer_task")
@patch("core_daemon.main.setup_websocket_logging")
def test_validation_exception_handler(
    mock_setup_ws_logging,
    mock_init_can_writer,
    mock_init_can_listeners,
    mock_initialize_app,
    mock_load_config,
    mock_get_paths,
    mock_configure_logger,
):
    """
    Tests the custom `validation_exception_handler` for `ResponseValidationError`.
    It verifies that when a response fails Pydantic validation, the handler
    catches the exception and returns a 500 status code with an appropriate error message.
    """
    from pydantic import BaseModel

    from core_daemon.main import app

    # Define a dummy route that can cause a ResponseValidationError
    # This is tricky because ResponseValidationError is usually raised by FastAPI internally
    # when response model validation fails.
    # We can simulate this by having an endpoint that tries to return invalid data
    # according to a response_model.
    class SimpleResponse(BaseModel):
        message: str
        count: int

    # This endpoint will try to return data that doesn't match SimpleResponse (missing 'count')
    @app.get("/test_validation_error", response_model=SimpleResponse)
    async def route_with_validation_error():
        return {"message": "hello"}  # Missing 'count', will cause ResponseValidationError

    client = TestClient(app)
    response = client.get("/test_validation_error")

    assert response.status_code == 500  # As per our handler
    assert "Validation error" in response.text
    # The exact text of 'exc' in "Validation error: {exc}" can be complex,
    # so checking for the prefix is often sufficient.


# It's important to also test the startup and shutdown events if they contain significant logic.
# This often involves mocking the functions called by these events.


@patch("core_daemon.main.initialize_can_writer_task")
@patch("core_daemon.main.setup_websocket_logging")
@patch("core_daemon.main.initialize_can_listeners")
@patch("core_daemon.main.configure_logger")
@patch("core_daemon.main.get_actual_paths")
@patch("core_daemon.main.load_config_data")
@patch("core_daemon.main.initialize_app_from_config")
def test_startup_events_called(
    mock_initialize_app,
    mock_load_config,
    mock_get_paths,
    mock_configure_logger,
    mock_init_can_listeners,
    mock_setup_ws_logging,
    mock_init_can_writer,
):
    """
    Tests that the FastAPI application's startup event handlers
    (initialize_can_writer_task, setup_websocket_logging, initialize_can_listeners)
    are called when the application starts.
    """
    # Import app here to ensure startup events are registered under patched conditions
    from core_daemon.main import app

    # Use TestClient to trigger startup events
    with TestClient(app):  # Removed unused _client variable (F841)
        # Startup events are called when the TestClient is initialized
        pass

    mock_init_can_writer.assert_called_once()
    mock_setup_ws_logging.assert_called_once()
    mock_init_can_listeners.assert_called_once()


# Test for prometheus_middleware_handler
# This middleware is applied to all HTTP requests.
@patch("core_daemon.main.prometheus_http_middleware")  # Mock the actual middleware logic
@patch("core_daemon.main.configure_logger")
@patch("core_daemon.main.get_actual_paths")
@patch("core_daemon.main.load_config_data")
@patch("core_daemon.main.initialize_app_from_config")
@patch("core_daemon.main.initialize_can_listeners")
@patch("core_daemon.main.initialize_can_writer_task")
@patch("core_daemon.main.setup_websocket_logging")
async def test_prometheus_middleware_called(
    mock_setup_ws_logging,
    mock_init_can_writer,
    mock_init_can_listeners,
    mock_initialize_app,
    mock_load_config,
    mock_get_paths,
    mock_configure_logger,
    mock_prometheus_logic,  # This is the one we want to check
):
    """
    Tests that the Prometheus middleware handler is correctly wired into the
    FastAPI application and is called for incoming requests.
    It mocks the underlying `prometheus_http_middleware` to verify the call.
    """
    from core_daemon.main import app

    # Define a simple async function for call_next
    async def dummy_call_next(request):
        return Response("OK")

    mock_prometheus_logic.return_value = Response(
        "MiddlewareProcessed"
    )  # Simulate middleware response

    # The middleware is an async function, so we need to call it with await
    # We need a mock request object

    # Directly test the handler function if possible, or use TestClient
    # Using TestClient is more of an integration test for the middleware.
    # To unit test the handler function itself:
    # from core_daemon.main import prometheus_middleware_handler
    # response = await prometheus_middleware_handler(mock_request, dummy_call_next)
    # mock_prometheus_logic.assert_called_once_with(mock_request, dummy_call_next)
    # assert response.body == b"MiddlewareProcessed"

    # Using TestClient to ensure it's wired up:
    client = TestClient(app)
    client.get("/")  # Hit any endpoint to trigger middleware

    # Check that our mocked prometheus_http_middleware was called
    # The call_next argument will be an internal FastAPI function, so use ANY
    mock_prometheus_logic.assert_called()
    # We can check the request part of the call if needed
    # call_args = mock_prometheus_logic.call_args[0]
    # Shorter comment: Check request part of call_args if needed  # Shortened E501

    # The response from the client will be what the *actual* endpoint returns,
    # unless the middleware itself returns a response without calling call_next.
    # If the middleware calls call_next, then the mocked logic's return value is
    # what call_next receives. Our mock_prometheus_logic is replacing the actual one.
    # If it was called, that's the main check for this unit test.
    # To check if the client got the middleware's response, the mock needs to be configured
    # such that it doesn't call call_next, or that call_next returns what the mock returns.
    # This gets complex. The primary goal here is to ensure the middleware *handler* in main.py
    # correctly calls the *imported* prometheus_http_middleware.

    # The assertion mock_prometheus_logic.assert_called() is the key.
    # If we want to test that the client sees the effect of the middleware,
    # we'd need the mock to behave like the real middleware (e.g., modify headers or return early).
    # For this test, knowing it's called is sufficient for main.py's responsibility.
