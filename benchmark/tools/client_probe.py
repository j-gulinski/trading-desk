import asyncio
import json
import threading
import time

import aiohttp
import httpx
import requests
import urllib3
from requests.adapters import HTTPAdapter

URL = "http://stub-core:9000/delay/200"
SECONDS = 10
IN_FLIGHT = (400, 1_000)


class Tally:
    def __init__(self):
        self.lock = threading.Lock()
        self.done = 0
        self.errors = 0

    def add(self, ok):
        with self.lock:
            if ok:
                self.done += 1
            else:
                self.errors += 1


def with_threads(call, in_flight):
    tally, stop = Tally(), time.monotonic() + SECONDS

    def work():
        while time.monotonic() < stop:
            try:
                call()
                tally.add(True)
            except Exception:
                tally.add(False)

    workers = [threading.Thread(target=work) for _ in range(in_flight)]
    started = time.process_time()
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    return tally, time.process_time() - started


async def on_loop(call, in_flight):
    tally, stop = Tally(), time.monotonic() + SECONDS

    async def work():
        while time.monotonic() < stop:
            try:
                await call()
                tally.add(True)
            except Exception:
                tally.add(False)

    started = time.process_time()
    await asyncio.gather(*(work() for _ in range(in_flight)))
    return tally, time.process_time() - started


def httpx_threads(in_flight):
    limits = httpx.Limits(max_connections=in_flight, max_keepalive_connections=in_flight)
    with httpx.Client(timeout=5, limits=limits) as client:
        return with_threads(lambda: client.get(URL).raise_for_status(), in_flight)


def requests_threads(in_flight):
    with requests.Session() as session:
        session.mount("http://", HTTPAdapter(pool_maxsize=in_flight))
        return with_threads(lambda: session.get(URL, timeout=5).raise_for_status(), in_flight)


def urllib3_threads(in_flight):
    pool = urllib3.PoolManager(maxsize=in_flight, timeout=5, retries=False)
    return with_threads(lambda: pool.request("GET", URL), in_flight)


async def httpx_async(in_flight):
    limits = httpx.Limits(max_connections=in_flight, max_keepalive_connections=in_flight)
    async with httpx.AsyncClient(timeout=5, limits=limits) as client:
        async def call():
            (await client.get(URL)).raise_for_status()
        return await on_loop(call, in_flight)


async def aiohttp_async(in_flight):
    connector = aiohttp.TCPConnector(limit=in_flight)
    async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=5)) as session:
        async def call():
            async with session.get(URL) as reply:
                await reply.read()
        return await on_loop(call, in_flight)


CLIENTS = [
    ("httpx", "threads", httpx_threads),
    ("requests", "threads", requests_threads),
    ("urllib3", "threads", urllib3_threads),
    ("httpx", "async", lambda n: asyncio.run(httpx_async(n))),
    ("aiohttp", "async", lambda n: asyncio.run(aiohttp_async(n))),
]

for name, model, run in CLIENTS:
    for in_flight in IN_FLIGHT:
        tally, cpu_seconds = run(in_flight)
        print(json.dumps({
            "client": name, "model": model, "in_flight": in_flight,
            "calls_per_s": round(tally.done / SECONDS),
            "cpu_ms_per_call": round(1000 * cpu_seconds / max(tally.done, 1), 3),
            "errors": tally.errors,
        }), flush=True)
