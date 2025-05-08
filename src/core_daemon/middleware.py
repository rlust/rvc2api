import time

from fastapi import Request

# Import metrics used by the middleware
from core_daemon.metrics import HTTP_LATENCY, HTTP_REQUESTS


async def prometheus_http_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    latency = time.perf_counter() - start

    path = request.url.path
    method = request.method
    status = response.status_code

    HTTP_REQUESTS.labels(method=method, endpoint=path, status_code=status).inc()
    HTTP_LATENCY.labels(method=method, endpoint=path).observe(latency)
    return response
