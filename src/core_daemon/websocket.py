import asyncio
import logging
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect

# Globals to hold active WebSocket clients
clients: Set[WebSocket] = set()
log_ws_clients: Set[WebSocket] = set()

logger = logging.getLogger(__name__)


# ── Log WebSocket Handler ──────────────────────────────────────────────────
class WebSocketLogHandler(logging.Handler):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop = loop

    def emit(self, record):
        log_entry = self.format(record)
        # Iterate over a copy of the set for safe removal if a client disconnects
        for ws_client in list(log_ws_clients):
            try:
                if self.loop and self.loop.is_running():
                    coro = ws_client.send_text(log_entry)
                    asyncio.run_coroutine_threadsafe(coro, self.loop)
            except Exception:
                log_ws_clients.discard(ws_client)  # Remove client if send fails


# ── Broadcasting ────────────────────────────────────────────────────────────
async def broadcast_to_clients(text: str):
    # This function will need WS_MESSAGES and WS_CLIENTS if they are to be updated here.
    # For now, assuming they are handled by the caller or a shared metrics module.
    # from .metrics import WS_MESSAGES, WS_CLIENTS # Example if metrics were used directly

    active_clients = list(clients)  # Create a copy for safe iteration
    for ws in active_clients:
        try:
            await ws.send_text(text)
            # WS_MESSAGES.inc() # Increment if metrics are handled here
        except Exception:
            clients.discard(ws)  # Remove client if send fails
    # WS_CLIENTS.set(len(clients)) # Update count if metrics are handled here


# ── WebSocket Endpoints ────────────────────────────────────────────────────
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket endpoint: push every new payload as JSON.
    """
    await ws.accept()
    clients.add(ws)
    # WS_CLIENTS.set(len(clients)) # Update count if metrics are handled here
    logger.info(f"WebSocket client connected: {ws.client.host}:{ws.client.port}")
    try:
        while True:
            await ws.receive_text()  # Keep connection alive, handle incoming messages if needed
    except WebSocketDisconnect:
        clients.discard(ws)
        # WS_CLIENTS.set(len(clients)) # Update count
        logger.info(f"WebSocket client disconnected: {ws.client.host}:{ws.client.port}")
    except Exception as e:
        clients.discard(ws)
        # WS_CLIENTS.set(len(clients)) # Update count
        logger.error(f"WebSocket error for client {ws.client.host}:{ws.client.port}: {e}")


async def websocket_logs_endpoint(ws: WebSocket):
    """
    WebSocket endpoint: stream all log messages in real time.
    """
    await ws.accept()
    log_ws_clients.add(ws)
    logger.info(f"Log WebSocket client connected: {ws.client.host}:{ws.client.port}")
    try:
        while True:
            await ws.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        log_ws_clients.discard(ws)
        logger.info(f"Log WebSocket client disconnected: {ws.client.host}:{ws.client.port}")
    except Exception as e:
        log_ws_clients.discard(ws)
        logger.error(f"Log WebSocket error for client {ws.client.host}:{ws.client.port}: {e}")
