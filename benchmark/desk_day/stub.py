import asyncio
import math
import random
import time

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from desk_day.universe import initial_price, stable_hash
from desk_runtime.config import env_int

LATENCY_SECONDS = env_int("STUB_LATENCY_MS", 200) / 1000
SEED = env_int("STUB_SEED", 1)

walks = {}


def next_price(sym):
    walk = walks.get(sym)
    if walk is None:
        walk = walks[sym] = [random.Random(SEED + stable_hash(sym)), initial_price(sym)]
    walk[1] *= math.exp(0.001 * walk[0].gauss(0, 1))
    return walk[1]


async def quote(request):
    await asyncio.sleep(LATENCY_SECONDS)
    sym = request.query_params.get("symbol", "").upper()
    previous = initial_price(sym)
    last = round(next_price(sym), 4)
    change = round(last - previous, 4)
    return JSONResponse({
        "c": last, "d": change, "dp": round(change / previous * 100, 4),
        "h": max(last, previous), "l": min(last, previous), "o": previous, "pc": previous,
        "t": int(time.time()),
    })


async def market_status(request):
    await asyncio.sleep(LATENCY_SECONDS)
    return JSONResponse({
        "exchange": "US", "isOpen": True, "session": "regular", "holiday": None,
        "t": int(time.time()),
    })


async def health(request):
    return JSONResponse({"status": "UP"})


async def unavailable(request):
    await asyncio.sleep(LATENCY_SECONDS)
    return JSONResponse({"error": "not served by the stub"}, status_code=503)


app = Starlette(routes=[
    Route("/health", health),
    Route("/finnhub/quote", quote),
    Route("/finnhub/stock/market-status", market_status),
    Route("/{path:path}", unavailable, methods=["GET", "POST"]),
])
