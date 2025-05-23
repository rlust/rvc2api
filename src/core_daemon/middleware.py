"""
Contains custom FastAPI middleware for the rvc2api application.

Middleware functions in this module are used to intercept HTTP requests
for purposes such as logging, metrics collection, or request modification.
"""

import time

from fastapi import Request

# Import metrics used by the middleware
from core_daemon.metrics import HTTP_LATENCY, HTTP_REQUESTS


async def prometheus_http_middleware(request: Request, call_next):
    """
    FastAPI middleware to record Prometheus metrics for HTTP requests.

    It measures the latency of each request and increments a counter for
    requests, labeled by method, endpoint, and status code.

    Args:
        request: The incoming FastAPI Request object.
        call_next: A function to call to process the request and get the response.

    Returns:
        The response object from the next handler in the chain.
    """
    start = time.perf_counter()
    response = await call_next(request)
    latency = time.perf_counter() - start

    path = request.url.path
    method = request.method
    status = response.status_code

    HTTP_REQUESTS.labels(method=method, endpoint=path, status_code=status).inc()
    HTTP_LATENCY.labels(method=method, endpoint=path).observe(latency)
    return response
