"""Type stub for httpx package."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)

class AsyncContextManagerProtocol(Protocol[T_co]):
    async def __aenter__(self) -> T_co: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

class Response:
    status_code: int
    text: str

    def json(self) -> dict[str, Any]: ...
    def raise_for_status(self) -> None: ...

# Define AsyncClient
class AsyncClient:
    def __init__(self, *, timeout: float | int | None = None) -> None: ...
    async def __aenter__(self) -> AsyncClient: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    async def post(
        self,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | int | None = None,
    ) -> Response: ...
    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | int | None = None,
    ) -> Response: ...
    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | int | None = None,
    ) -> Response: ...
