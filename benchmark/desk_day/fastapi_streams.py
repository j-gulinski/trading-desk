import asyncio
import importlib
import threading
from contextlib import asynccontextmanager

import uvicorn
from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from desk_runtime.config import SERVICE_PORTS
from desk_runtime.http import install_json_errors
from desk_runtime.logging_config import configure_logging, get_logger
from desk_runtime.serialization import to_json
from desk_runtime.service_runtime import install_default_health
from desk_runtime.streams import HEARTBEAT_SECONDS

STREAMS = {
    "market-data-service": ("market_data_service", "publisher", "/stream", 500),
    "pricing-service": ("pricing_service", "valuation_publisher", "/valuation-stream", 5000),
}


class AsyncHub:
    """EventHub for an asyncio server: publish from any thread, stream on the event loop."""

    def __init__(self, log, queue_size):
        self._log = log
        self._queue_size = queue_size
        self._clients = set()
        self.loop = None

    def publish(self, event_type, data):
        frame = f"event: {event_type}\ndata: {to_json(data)}\n\n"
        try:
            self.loop.call_soon_threadsafe(self._fan_out, event_type, frame)
        except (AttributeError, RuntimeError):
            pass

    def _fan_out(self, event_type, frame):
        for client in list(self._clients):
            try:
                client.put_nowait(frame)
            except asyncio.QueueFull:
                self._clients.discard(client)
                client.shutdown(immediate=True)
                self._log.warning("stream_client_overflow_reconnect_required", event_type=event_type)

    async def subscribe(self):
        client = asyncio.Queue(maxsize=self._queue_size)
        self._clients.add(client)
        self._log.info("stream_client_connected")
        try:
            yield ": connected\n\n"
            while True:
                try:
                    frame = client.get_nowait()
                except asyncio.QueueEmpty:
                    try:
                        frame = await asyncio.wait_for(client.get(), HEARTBEAT_SECONDS)
                    except TimeoutError:
                        frame = ": ping\n\n"
                yield frame
        except asyncio.QueueShutDown:
            pass
        finally:
            self._clients.discard(client)
            self._log.info("stream_client_disconnected")


def create_app(bottle_app, background, hub, stream_path):
    @asynccontextmanager
    async def lifespan(app):
        hub.loop = asyncio.get_running_loop()
        for target in background:
            threading.Thread(target=target, daemon=True).start()
        yield
        hub.loop = None

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get(stream_path)
    async def stream():
        return StreamingResponse(
            hub.subscribe(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    app.mount("/", WSGIMiddleware(bottle_app, workers=40))
    return app


def run(service_name):
    package, publisher, stream_path, queue_size = STREAMS[service_name]
    configure_logging(service_name)
    log = get_logger(service_name)
    log.info("starting")
    hub = AsyncHub(log, queue_size)
    importlib.import_module(f"{package}.{publisher}").hub = hub
    bottle_app, background = importlib.import_module(f"{package}.main").build()
    install_default_health(bottle_app, service_name)
    install_json_errors(bottle_app)
    uvicorn.run(
        create_app(bottle_app, background, hub, stream_path),
        host="0.0.0.0", port=SERVICE_PORTS[service_name], log_level="warning",
        access_log=False, timeout_graceful_shutdown=5,
    )
