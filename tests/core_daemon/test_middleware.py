"""
Tests for the HTTP middleware, specifically the Prometheus metrics middleware.

This module verifies that the `prometheus_http_middleware` correctly:
- Records HTTP request counts, labeled by method, endpoint, and status code.
- Records HTTP request latency, labeled by method and endpoint.
- Handles different paths, methods, and response statuses accurately.
- Isolates metrics for different requests.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from core_daemon.metrics import HTTP_LATENCY, HTTP_REQUESTS
from core_daemon.middleware import prometheus_http_middleware


# Reset metrics before each test to ensure isolation
@pytest.fixture(autouse=True)
def reset_metrics():
    """Fixture to clear Prometheus metrics before each test.

    Ensures test isolation by resetting HTTP_REQUESTS and HTTP_LATENCY
    metrics, including their labeled child metrics.
    """
    # For Counters, you might need to access the internal _value if using prometheus_client directly
    # or re-initialize them if they don't have a clear/reset method.
    # A common way is to unregister and re-register, or clear children if labels are used.
    # For simplicity here, we'll assume direct re-initialization or a hypothetical reset.
    # If using labels, clearing children is important:
    HTTP_REQUESTS.clear()
    HTTP_LATENCY.clear()


@pytest.mark.asyncio
async def test_prometheus_http_middleware_records_metrics():
    """
    Tests that the prometheus_http_middleware correctly records count and latency
    for successful HTTP requests.
    """
    app = FastAPI()

    # Apply the middleware
    @app.middleware("http")
    async def middleware_wrapper(request: Request, call_next):
        return await prometheus_http_middleware(request, call_next)

    # Define a simple endpoint
    @app.get("/test_path")
    async def test_endpoint():
        return PlainTextResponse("OK", status_code=200)

    client = TestClient(app)

    # Store current metric values before the request
    # For counters with labels, we need to get the specific labeled value
    # If the label combination hasn't been used, trying to get its value might error
    # or return 0 depending on the Prometheus client library version.
    # It's often easier to check the change after the request.

    initial_requests_total = HTTP_REQUESTS.labels(
        method="GET", endpoint="/test_path", status_code="200"
    )._value
    initial_latency_count = HTTP_LATENCY.labels(method="GET", endpoint="/test_path")._count
    initial_latency_sum = HTTP_LATENCY.labels(method="GET", endpoint="/test_path")._sum

    # Make a request
    response = client.get("/test_path")
    assert response.status_code == 200
    assert response.text == "OK"

    # Check that metrics were updated
    # Counter
    assert (
        HTTP_REQUESTS.labels(method="GET", endpoint="/test_path", status_code="200")._value
        == initial_requests_total + 1
    )

    # Histogram
    # We expect the count to increase by 1
    assert (
        HTTP_LATENCY.labels(method="GET", endpoint="/test_path")._count == initial_latency_count + 1
    )
    # The sum should also increase by some positive value (the latency)
    assert HTTP_LATENCY.labels(method="GET", endpoint="/test_path")._sum > initial_latency_sum


@pytest.mark.asyncio
async def test_prometheus_http_middleware_handles_different_paths_and_methods():
    """
    Tests that the prometheus_http_middleware correctly records metrics
    for various paths, HTTP methods, and response status codes.
    It also verifies that metrics for one endpoint do not affect others.
    """
    app = FastAPI()

    @app.middleware("http")
    async def middleware_wrapper(request: Request, call_next):
        return await prometheus_http_middleware(request, call_next)

    @app.get("/path1")
    async def get_path1():
        return PlainTextResponse("OK GET path1", status_code=200)

    @app.post("/path2")
    async def post_path2():
        return PlainTextResponse("OK POST path2", status_code=201)

    @app.get("/path_error")
    async def get_path_error():
        return PlainTextResponse("Error", status_code=500)

    client = TestClient(app)

    # Request 1
    client.get("/path1")
    assert HTTP_REQUESTS.labels(method="GET", endpoint="/path1", status_code="200")._value == 1
    assert HTTP_LATENCY.labels(method="GET", endpoint="/path1")._count == 1

    # Request 2
    client.post("/path2")
    assert HTTP_REQUESTS.labels(method="POST", endpoint="/path2", status_code="201")._value == 1
    assert HTTP_LATENCY.labels(method="POST", endpoint="/path2")._count == 1

    # Request 3 (error)
    client.get("/path_error")
    assert HTTP_REQUESTS.labels(method="GET", endpoint="/path_error", status_code="500")._value == 1
    assert HTTP_LATENCY.labels(method="GET", endpoint="/path_error")._count == 1

    # Check that metrics for one request don't affect others
    assert HTTP_REQUESTS.labels(method="GET", endpoint="/path1", status_code="200")._value == 1
    assert HTTP_REQUESTS.labels(method="POST", endpoint="/path2", status_code="201")._value == 1
