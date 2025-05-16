"""
Type stub file for FastAPI to improve pylance type checking.

This file provides type hints for commonly used FastAPI components.
Uses Python 3.9+ typing syntax with | for unions and builtin collection types.

Note: The non-snake_case function name Body() is exempted from linting rules
in pyproject.toml using [tool.ruff.lint.per-file-ignores] configuration.
"""

from typing import Any, Generic, TypeVar

# Types
T = TypeVar("T")

class Annotated(Generic[T]): ...

# Request class
class Request:
    url: URL
    method: str

class URL:
    path: str

class Response:
    status_code: int

# WebSocket classes
class WebSocket:
    client: Any
    async def accept(self) -> None: ...
    async def close(self, code: int = 1000) -> None: ...
    async def send_text(self, data: str) -> None: ...
    async def send_json(self, data: Any) -> None: ...
    async def send_bytes(self, data: bytes) -> None: ...
    async def receive_text(self) -> str: ...
    async def receive_json(self) -> Any: ...
    async def receive_bytes(self) -> bytes: ...

class WebSocketDisconnect(Exception):
    code: int
    def __init__(self, code: int = 1000) -> None: ...

class WebSocketException(Exception): ...

# Core FastAPI class
class FastAPI:
    state: Any

    def __init__(
        self,
        *,
        debug: bool = False,
        title: str = "FastAPI",
        description: str = "",
        version: str = "0.1.0",
        openapi_url: str | None = "/openapi.json",
        docs_url: str | None = "/docs",
        redoc_url: str | None = "/redoc",
        root_path: str = "",
        servers: list[dict[str, str]] | None = None,
        lifespan: Any = None,
    ) -> None: ...
    def mount(self, path: str, app: Any, name: str | None = None) -> None: ...
    def middleware(self, middleware_type: str) -> Any: ...
    def exception_handler(self, exc_class_or_status_code: Any) -> Any: ...
    def get(
        self,
        path: str,
        *,
        response_model: Any = None,
        status_code: int | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = "Successful Response",
        **kwargs: Any,
    ) -> Any: ...
    def include_router(
        self,
        router: Any,
        *,
        prefix: str = "",
        tags: list[str] | None = None,
        dependencies: list[Any] | None = None,
        responses: dict[int | str, dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None: ...

# Define the possible types for examples
examples_type = dict[str, Any] | list[Any] | dict[str, dict[str, str | dict[str, Any]]] | None

# Parameter declarations
def Body(
    default: Any = ...,
    *,
    embed: bool = False,
    media_type: str = "application/json",
    title: str | None = None,
    description: str | None = None,
    gt: float | None = None,
    ge: float | None = None,
    lt: float | None = None,
    le: float | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    regex: str | None = None,
    example: Any = None,
    examples: examples_type = None,
) -> Any: ...

# For backward compatibility
body_param: Any = Body
