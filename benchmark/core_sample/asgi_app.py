import asyncio
import time
from contextlib import asynccontextmanager

import aiohttp
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from core_sample.core import (
    IN_FLIGHT, INSERT_ORDER, PROVIDER_TIMEOUT_SECONDS, PROVIDER_URL, TICK_SECONDS, UPDATE_POSITION,
    UPDATES_PER_SECOND, Ingest, known_position, new_order, order_result, valuation_update,
)
from desk_runtime.config import DATABASE_MAX_OVERFLOW, DATABASE_POOL_SIZE, env_required
from desk_runtime.serialization import to_json

engine = create_async_engine(
    env_required("DATABASE_URL"), pool_size=DATABASE_POOL_SIZE, max_overflow=DATABASE_MAX_OVERFLOW,
)
provider = None
ingest = None
tasks = set()


class StreamHub:
    """The event-loop counterpart of desk_runtime's EventHub: same frames, same queue limit."""

    QUEUE_SIZE = 500

    def __init__(self):
        self.clients = set()

    def publish(self, event_type, data):
        frame = f"event: {event_type}\ndata: {to_json(data)}\n\n"
        for client in list(self.clients):
            try:
                client.put_nowait(frame)
            except asyncio.QueueFull:
                self.disconnect(client)

    async def subscribe(self):
        client = asyncio.Queue(maxsize=self.QUEUE_SIZE)
        self.clients.add(client)
        try:
            yield ": connected\n\n"
            while (frame := await client.get()) is not None:
                yield frame
        finally:
            self.clients.discard(client)

    def disconnect(self, client):
        self.clients.discard(client)
        while not client.empty():
            client.get_nowait()
        client.put_nowait(None)


hub = StreamHub()


def start_task(coroutine):
    task = asyncio.create_task(coroutine)
    tasks.add(task)
    task.add_done_callback(tasks.discard)


async def refresh(limit, instrument, due):
    async with limit:
        if ingest.is_late(due):
            return
        try:
            async with provider.get(PROVIDER_URL) as reply:
                await reply.read()
                ok = reply.status == 200
        except (aiohttp.ClientError, TimeoutError):
            ok = False
        if ok:
            ingest.stored(instrument)
        else:
            ingest.count("errors")


async def run_ingest():
    limit = asyncio.Semaphore(IN_FLIGHT)
    while True:
        await asyncio.sleep(TICK_SECONDS)
        for instrument, due in ingest.tick():
            start_task(refresh(limit, instrument, due))


async def publish_valuations():
    next_at = time.monotonic()
    while True:
        next_at += 1 / UPDATES_PER_SECOND
        await asyncio.sleep(max(0.0, next_at - time.monotonic()))
        hub.publish("valuation", valuation_update())


@asynccontextmanager
async def lifespan(app):
    global provider
    provider = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=IN_FLIGHT),
        timeout=aiohttp.ClientTimeout(total=PROVIDER_TIMEOUT_SECONDS),
    )
    start_task(publish_valuations())
    yield
    await provider.close()
    await engine.dispose()


app = FastAPI(lifespan=lifespan)


def json_response(data, status=200):
    return Response(to_json(data), status_code=status, media_type="application/json")


@app.get("/health")
async def health():
    return json_response({"status": "ok"})


@app.post("/ingest/{period}")
async def start_ingest(period: int):
    global ingest
    if ingest:
        return json_response({"error": "ingestion already running"}, 409)
    ingest = Ingest(period)
    start_task(run_ingest())
    return json_response({"period": period})


@app.get("/ingest/stats")
async def ingest_stats():
    if not ingest:
        return json_response({"error": "ingestion not started"}, 404)
    return json_response(ingest.stats())


@app.post("/orders/{instrument}/{book}")
async def place_order(instrument: int, book: int):
    if not known_position(instrument, book):
        return json_response({"error": "unknown position"}, 404)
    order = new_order(instrument, book)
    async with engine.begin() as connection:
        await connection.execute(text(INSERT_ORDER), order)
        position = (await connection.execute(text(UPDATE_POSITION), order)).scalar_one()
    return json_response(order_result(order, position), 201)


@app.get("/valuations/stream")
async def valuation_stream():
    return StreamingResponse(
        hub.subscribe(), headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
    )
