"""
api_routers

This package contains FastAPI APIRouter modules that define the various API endpoints
for the rvc2api application. Each router handles a specific domain of functionality
to maintain separation of concerns.

Routers:
    - can: Endpoints for CAN bus operations and message handling
    - config_and_ws: Configuration and WebSocket connection endpoints
    - entities: Endpoints for interacting with RV-C entities
"""

from .can import api_router_can
from .config_and_ws import api_router_config_ws
from .entities import api_router_entities

__all__ = ["api_router_can", "api_router_config_ws", "api_router_entities"]
