import threading
import time
from concurrent.futures import ThreadPoolExecutor

import structlog
import urllib3
from bottle import Bottle, abort, response
from sqlalchemy import create_engine, text

from core_sample.core import (
    IN_FLIGHT, INSERT_ORDER, PROVIDER_TIMEOUT_SECONDS, PROVIDER_URL, TICK_SECONDS, UPDATE_POSITION,
    UPDATES_PER_SECOND, Ingest, known_position, new_order, order_result, valuation_update,
)
from desk_runtime.config import DATABASE_MAX_OVERFLOW, DATABASE_POOL_SIZE, env_required
from desk_runtime.http import install_json_errors, json_response
from desk_runtime.streams import EventHub

engine = create_engine(
    env_required("DATABASE_URL"), pool_size=DATABASE_POOL_SIZE, max_overflow=DATABASE_MAX_OVERFLOW,
)
provider = urllib3.PoolManager(maxsize=IN_FLIGHT, timeout=PROVIDER_TIMEOUT_SECONDS, retries=False)
hub = EventHub(structlog.get_logger())
ingest = None
app = Bottle()
install_json_errors(app)


def refresh(instrument, due):
    if ingest.is_late(due):
        return
    try:
        ok = provider.request("GET", PROVIDER_URL).status == 200
    except urllib3.exceptions.HTTPError:
        ok = False
    if ok:
        ingest.stored(instrument)
    else:
        ingest.count("errors")


def run_ingest():
    pool = ThreadPoolExecutor(IN_FLIGHT)
    while True:
        time.sleep(TICK_SECONDS)
        for instrument, due in ingest.tick():
            pool.submit(refresh, instrument, due)


def publish_valuations():
    next_at = time.monotonic()
    while True:
        next_at += 1 / UPDATES_PER_SECOND
        time.sleep(max(0.0, next_at - time.monotonic()))
        hub.publish("valuation", valuation_update())


@app.get("/health")
def health():
    return json_response({"status": "ok"})


@app.post("/ingest/<period:int>")
def start_ingest(period):
    global ingest
    if ingest:
        abort(409, "ingestion already running")
    ingest = Ingest(period)
    threading.Thread(target=run_ingest, daemon=True).start()
    return json_response({"period": period})


@app.get("/ingest/stats")
def ingest_stats():
    if not ingest:
        abort(404, "ingestion not started")
    return json_response(ingest.stats())


@app.post("/orders/<instrument:int>/<book:int>")
def place_order(instrument, book):
    if not known_position(instrument, book):
        abort(404, "unknown position")
    order = new_order(instrument, book)
    with engine.begin() as connection:
        connection.execute(text(INSERT_ORDER), order)
        position = connection.execute(text(UPDATE_POSITION), order).scalar_one()
    return json_response(order_result(order, position), status=201)


@app.get("/valuations/stream")
def valuation_stream():
    response.content_type = "text/event-stream"
    response.set_header("Cache-Control", "no-cache")
    return hub.subscribe()


threading.Thread(target=publish_valuations, daemon=True).start()
