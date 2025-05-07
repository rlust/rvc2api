import asyncio
import logging

# Define the `log_ws_clients` set to resolve the undefined name error
log_ws_clients: set = set()


class WebSocketLogHandler(logging.Handler):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop = loop

    def emit(self, record):
        log_entry = self.format(record)
        for ws_client in list(log_ws_clients):
            try:
                if self.loop and self.loop.is_running():
                    coro = ws_client.send_text(log_entry)
                    asyncio.run_coroutine_threadsafe(coro, self.loop)
            except Exception:
                log_ws_clients.discard(ws_client)
