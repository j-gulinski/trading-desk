import os
import time
import threading
import queue
import json
import random
import logging
import bottle
from bottle import run, response, ServerAdapter
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn

from shared import INSTRUMENTS, get_iso_timestamp

TIME_INTERVAL_MS = os.getenv("TIME_INTERVAL_MS", 100)

app = bottle.Bottle()

lock = threading.Lock()
ticks_generated = 0
last_event_timestamp = None
client_event_queues = []
snapshot = {}
queues = {}
ticks_kept = 100

for inst in INSTRUMENTS.values():
    data = {
        "asset_type": inst["type"],
        "instrument_id": inst["instrument_id"],
        "market_symbol": inst["market_symbol"],
    }

    if inst["type"] == "BOND":
        data.update(
            {
                "face_value": inst["face_value"],
                "coupon_rate": inst["coupon_rate"],
                "maturity_years": inst["maturity_years"],
                "payments_per_year": inst["payments_per_year"],
            }
        )
    elif inst["type"] == "FX_FORWARD":
        data["tenor_years"] = inst["tenor_years"]

    snapshot[inst["instrument_id"]] = data
    queues[inst["market_symbol"]] = queue.Queue()

snapshot["EQ_ACME"].update({"bid": 99.95, "ask": 100.05, "last": 100.00})
snapshot["BOND_GOVT_5Y"].update({"yield": 0.05})
# order in pair (?)
snapshot["FX_EURUSD_1Y"].update(
    {"spot": 1.16, "domestic_rate": 0.0375, "foreign_rate": 0.0215}
)


def generate_equity_tick(timestamp):
    global ticks_generated, last_event_timestamp, snapshot

    current_equity_mid = (snapshot["EQ_ACME"]["bid"] + snapshot["EQ_ACME"]["ask"]) / 2

    new_equity_mid = max(1.0, current_equity_mid + random.uniform(-0.2, 0.2))

    equity_tick = {
        "event_id": ticks_generated,
        "timestamp": timestamp,
        "instrument_id": snapshot["EQ_ACME"]["instrument_id"],
        "asset_type": snapshot["EQ_ACME"]["asset_type"],
        "market_symbol": snapshot["EQ_ACME"]["market_symbol"],
        "bid": round(new_equity_mid - 0.05, 4),
        "ask": round(new_equity_mid + 0.05, 4),
        "last": round(new_equity_mid + random.uniform(-0.02, 0.02), 4),
    }
    snapshot["EQ_ACME"].update(
        {
            "bid": equity_tick["bid"],
            "ask": equity_tick["ask"],
            "last": equity_tick["last"],
        }
    )

    return equity_tick


def generate_bond_tick(timestamp):
    global ticks_generated, last_event_timestamp, snapshot

    current_bond_yield = snapshot["BOND_GOVT_5Y"]["yield"]
    new_bond_yield = max(
        0.03, min(0.06, current_bond_yield + random.uniform(-0.003, 0.003))
    )

    bond_tick = {
        "event_id": ticks_generated,
        "timestamp": timestamp,
        "instrument_id": snapshot["BOND_GOVT_5Y"]["instrument_id"],
        "asset_type": snapshot["BOND_GOVT_5Y"]["asset_type"],
        "market_symbol": snapshot["BOND_GOVT_5Y"]["market_symbol"],
        "yield": round(new_bond_yield, 4),
    }
    snapshot["BOND_GOVT_5Y"].update({"yield": bond_tick["yield"]})

    return bond_tick


def generate_fx_forward_tick(timestamp):
    global ticks_generated, last_event_timestamp, snapshot

    current_spot = snapshot["FX_EURUSD_1Y"]["spot"]
    new_spot = max(1.10, min(1.20, current_spot + random.uniform(-0.01, 0.01)))

    fx_forward_tick = {
        "event_id": ticks_generated,
        "timestamp": timestamp,
        "instrument_id": snapshot["FX_EURUSD_1Y"]["instrument_id"],
        "asset_type": snapshot["FX_EURUSD_1Y"]["asset_type"],
        "market_symbol": snapshot["FX_EURUSD_1Y"]["market_symbol"],
        "spot": round(new_spot, 4),
        "domestic_rate": snapshot["FX_EURUSD_1Y"]["domestic_rate"],
        "foreign_rate": snapshot["FX_EURUSD_1Y"]["foreign_rate"],
    }
    snapshot["FX_EURUSD_1Y"].update({"spot": fx_forward_tick["spot"]})

    return fx_forward_tick


def market_data_generator():
    global ticks_generated, last_event_timestamp, snapshot

    while True:
        now = get_iso_timestamp()
        tick = None

        with lock:
            tick_type = random.choice(["EQUITY", "BOND", "FX_FORWARD"])
            if tick_type == "EQUITY":
                tick = generate_equity_tick(now)
            elif tick_type == "BOND":
                tick = generate_bond_tick(now)
            elif tick_type == "FX_FORWARD":
                tick = generate_fx_forward_tick(now)

            if queues[tick["market_symbol"]].qsize() == ticks_kept:
                queues[tick["market_symbol"]].get()
            queues[tick["market_symbol"]].put(tick)

            logging.debug(f"Generated tick for {tick['market_symbol']}: {tick}")

            ticks_generated += 1
            last_event_timestamp = now
            logging.debug(f"Total ticks generated: {ticks_generated}")

            for q in client_event_queues:
                q.put(tick)

        time.sleep(TIME_INTERVAL_MS / 1000.0)


@app.route("/stream")
def stream():
    response.content_type = "text/event-stream"

    client_q = queue.Queue()
    logging.info("New client connected to /stream endpoint")

    with lock:
        client_event_queues.append(client_q)

    def generate_events():
        try:
            while True:
                tick = client_q.get()
                yield f"data: {json.dumps(tick)}\n\n"
        except Exception:
            pass
        finally:
            with lock:
                if client_q in client_event_queues:
                    client_event_queues.remove(client_q)
                    logging.info("Client disconnected from /stream endpoint")

    return generate_events()


@app.route("/snapshot")
def get_snapshot():
    response.content_type = "application/json"
    with lock:
        return json.dumps(snapshot)


@app.route("/history/<symbol>")
def get_history(symbol):
    response.content_type = "application/json"
    with lock:
        queue = queues.get(symbol)
        if queue:
            return json.dumps(list(queue.queue))
        return json.dumps([])


@app.route("/health")
def health():
    global ticks_generated, last_event_timestamp

    with lock:
        return {
            "service": "market-data-service",
            "status": "UP",
            "generated_events": ticks_generated,
            "last_event_timestamp": last_event_timestamp,
        }


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = make_server(
            self.host, self.port, handler, server_class=ThreadingWSGIServer
        )
        server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Market Data Service...")
    threading.Thread(target=market_data_generator, daemon=True).start()
    app.run(host="0.0.0.0", port=8001, server=ThreadedServer)
