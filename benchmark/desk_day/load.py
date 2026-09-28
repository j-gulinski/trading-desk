"""K clients watch the desk's price and valuation streams while the desk trades at a fixed rate."""

import argparse
import asyncio
import json
import math
import random
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import uvloop

from desk_day.universe import EQUITY_BOOKS, HELD_SYMBOLS, OPTION_CURVE
from desk_runtime.config import DEFAULT_QUOTE_PROVIDER, SERVICE_URLS

PRICING = SERVICE_URLS["pricing-service"]
BOOKS = SERVICE_URLS["books-service"]
TRADE_ACTIONS = f"{SERVICE_URLS['trade-action-service']}/trade-actions"
STREAMS = [
    urlsplit(f"{SERVICE_URLS['market-data-service']}/stream"),
    urlsplit(f"{PRICING}/valuation-stream"),
]
READ_TIMEOUT = 8
WRITE_TIMEOUT = 6
QUIET = 30
GIVE_UP = 120
RECONNECT = 2
CLOSE_AFTER = 60
HEALTH_EVERY = 10
MEASURE = 150
SAMPLED = 10
OPEN_RATE = 0.2
PREVIEW_RATE = 0.2
HELD = set(HELD_SYMBOLS)
PREVIEW = {
    "asset_class": "EUROPEAN_OPTION", "symbol": "EUROPEAN_OPTION", "market_data_provider": "FINNHUB",
    "terms": {
        "model": "BLACK_SCHOLES", "underlying_symbol": HELD_SYMBOLS[0], "option_type": "CALL",
        "strike": "100", "maturity_years": "1", "discount_curve": OPTION_CURVE,
        "multiplier": 1, "volatility": 0.22,
    },
}


def p95(values):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[math.ceil(0.95 * len(ordered)) - 1], 2)


def ms_since(iso_time, now):
    return (now - datetime.fromisoformat(iso_time).timestamp()) * 1000


def outcome(status):
    if 200 <= status < 300:
        return "ok"
    if 400 <= status < 500:
        return "rejected"
    return "error"


async def read(reader, chunked):
    if not chunked:
        return await reader.read(65536)
    size = int((await reader.readline()).split(b";")[0], 16)
    return (await reader.readexactly(size + 2))[:-2]


class Load:
    def __init__(self, client):
        self.client = client
        self.start = math.inf
        self.live = 0
        self.events = []
        self.board = {}
        self.first_seen = {}
        self.confirmed = {}
        self.lags = []
        self.samples = {"tick": [], "valuation": [], "execution": []}
        self.outcomes = {"open": Counter(), "close": Counter()}

    async def hold(self, url, index, delay):
        await asyncio.sleep(delay)
        sampled = index < SAMPLED
        while True:
            writer = None
            opened = False
            try:
                async with asyncio.timeout(READ_TIMEOUT):
                    reader, writer = await asyncio.open_connection(url.hostname, url.port)
                    writer.write(f"GET {url.path} HTTP/1.1\r\nHost: {url.netloc}\r\n"
                                 "Accept: text/event-stream\r\nConnection: close\r\n\r\n".encode())
                    head = (await reader.readuntil(b"\r\n\r\n")).lower()
                if not head.startswith((b"http/1.1 200", b"http/1.0 200")):
                    raise ConnectionError(head.split(b"\r\n")[0])
                opened = True
                self.live += 1
                self.events.append((time.time(), "open"))
                chunked = sampled and b"transfer-encoding: chunked" in head
                text = b""
                spots = {}
                while data := await asyncio.wait_for(read(reader, chunked), READ_TIMEOUT):
                    if sampled:
                        *frames, text = (text + data).split(b"\n\n")
                        for frame in frames:
                            self.on_frame(index, spots, frame)
            except (OSError, TimeoutError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                pass
            if opened:
                self.live -= 1
            if writer is not None:
                writer.close()
            self.events.append((time.time(), "drop"))
            await asyncio.sleep(RECONNECT)

    def on_frame(self, index, spots, frame):
        now = time.time()
        fields = {}
        for line in frame.split(b"\n"):
            name, _, value = line.partition(b":")
            fields[name] = value
        try:
            event = fields.get(b"event", b"").strip()
            data = json.loads(fields.get(b"data", b"{}"))
            if event == b"market_tick":
                self.on_tick(index, data, now)
            elif event == b"valuation_update":
                self.on_valuation(index, spots, data, now)
        except (ValueError, KeyError, TypeError, AttributeError):
            pass

    def on_tick(self, index, data, now):
        if now >= self.start:
            self.samples["tick"].append(ms_since(data["received_at"], now))
        if index == 0 and data["symbol"] in HELD and data["provider"] == DEFAULT_QUOTE_PROVIDER:
            self.board[data["symbol"]] = data

    def on_valuation(self, index, spots, data, now):
        trade_id = data["trade_id"]
        if index == 0:
            self.first_seen.setdefault(trade_id, now)
        spot_source = (data.get("valuation_payload") or {}).get("spot_source") or {}
        received = spot_source.get("received_at")
        if not received or received <= spots.get(trade_id, ""):
            return
        if trade_id in spots and now >= self.start:
            self.samples["valuation"].append(ms_since(received, now))
        spots[trade_id] = received

    async def execute(self, action, body):
        started = time.time()
        status, text = 0, ""
        try:
            response = await self.client.post(TRADE_ACTIONS, json=body, timeout=WRITE_TIMEOUT)
            status, text = response.status_code, response.text
            self.samples["execution"].append((time.time() - started) * 1000)
        except httpx.HTTPError:
            pass
        self.outcomes[action][outcome(status)] += 1
        return status, text

    async def trade(self, books):
        if not self.board:
            self.outcomes["open"]["no_quote"] += 1
            return
        symbol = random.choice(list(self.board))
        quote = self.board[symbol]
        book = random.choice(books)
        status, text = await self.execute("open", {
            "action_type": "OPEN_TRADE", "client_request_id": f"manual-open-{uuid.uuid4()}",
            "symbol": symbol, "book_id": book["book_id"], "asset_class": book["expected_asset_class"],
            "side": "BUY", "quantity": random.randint(1, 20), "currency": quote["currency"],
            "market_data_provider": quote["provider"], "client_seen_price": quote["buy_price"],
            "source": "TRADING_TICKET",
        })
        if status != 201:
            return
        trade_id = json.loads(text)["trade_id"]
        self.confirmed[trade_id] = time.time()
        if self.confirmed[trade_id] + CLOSE_AFTER < self.start + MEASURE:
            await asyncio.sleep(CLOSE_AFTER)
            await self.execute("close", {
                "action_type": "CLOSE_TRADE", "trade_id": trade_id, "close_reason": "MANUAL_CLOSE",
                "client_seen_price": self.board[symbol]["sell_price"], "client_request_id": str(uuid.uuid4()),
            })

    async def watch_pricing(self):
        while True:
            try:
                last = (await self.client.get(f"{PRICING}/health")).json()["last_market_event_time"]
                self.lags.append(time.time() - datetime.fromisoformat(last).timestamp())
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                pass
            await asyncio.sleep(HEALTH_EVERY)

    def summary(self, client_cores):
        self.samples["position"] = [max(0.0, self.first_seen[trade_id] - at) * 1000
                                    for trade_id, at in self.confirmed.items() if trade_id in self.first_seen]
        return {
            "stable_at": self.start,
            "p95_ms": {name: p95(values) for name, values in self.samples.items()},
            "pricing_lag_p95_s": p95(self.lags),
            "opens": self.outcomes["open"],
            "closes": self.outcomes["close"],
            "streams_opened": sum(name == "open" for _, name in self.events),
            "streams_dropped": sum(name == "drop" and at >= self.start for at, name in self.events),
            "client_cores": round(client_cores, 3),
        }


async def run(k, out):
    out.mkdir(parents=True, exist_ok=True)
    rate = max(1.0, k / 10)
    async with httpx.AsyncClient(timeout=READ_TIMEOUT) as client:
        books = [book for book in (await client.get(f"{BOOKS}/books")).json() if book["name"] in EQUITY_BOOKS]
        load = Load(client)
        # Stage 1: clients connect at K/10 per second; stable = all 2K streams open and 30 s without a change
        give_up_at = time.time() + (k - 1) / rate + GIVE_UP
        tasks = [asyncio.create_task(load.hold(url, i, i / rate)) for i in range(k) for url in STREAMS]
        while not (load.live == 2 * k and time.time() - load.events[-1][0] >= QUIET):
            if time.time() > give_up_at:
                (out / "unstable").write_text(json.dumps({"live": load.live, "expected": 2 * k}) + "\n")
                return 2
            await asyncio.sleep(0.5)
        stable = time.time()
        (out / "stable").write_text(f"{stable}\n")
        # Stage 2: measured window with previews, trading and pricing health
        load.start = stable
        cpu_from = time.process_time()
        oha = await asyncio.create_subprocess_exec(
            "oha", "-z", f"{MEASURE}s", "-q", f"{PREVIEW_RATE:g}", "-t", f"{WRITE_TIMEOUT}s",
            "--no-tui", "--output-format", "json", "-m", "POST", "-H", "Content-Type: application/json",
            "-d", json.dumps(PREVIEW), f"{PRICING}/price", stdout=asyncio.subprocess.PIPE)
        tasks.append(asyncio.create_task(load.watch_pricing()))
        for i in range(int(MEASURE * OPEN_RATE)):
            await asyncio.sleep(max(0.0, stable + i / OPEN_RATE - time.time()))
            tasks.append(asyncio.create_task(load.trade(books)))
        await asyncio.sleep(stable + MEASURE - time.time())
        client_cores = (time.process_time() - cpu_from) / (time.time() - stable)
        for task in tasks:
            task.cancel()
        # Stage 3: write what happened inside the window
        (out / "preview.json").write_bytes((await oha.communicate())[0])
        (out / "summary.json").write_text(json.dumps(load.summary(client_cores), indent=2) + "\n")
        (out / "done").write_text(f"{time.time()}\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    raise SystemExit(uvloop.run(run(args.clients, Path(args.out))))
