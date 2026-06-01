import time
import random
import logging
import threading

from app import persistence
from app.config import TICK_INTERVAL_MS
from app.publisher import publish_tick
from shared.functions import get_iso_timestamp


def generate_equity_tick():
    last = persistence.spots["ACME"]
    mid = max(1.0, last["mid"] + random.uniform(-0.2, 0.2))
    half_spread = random.uniform(0.03, 0.08)
    return {
        "symbol": "ACME", "asset_class": "EQUITY", "currency": "USD",
        "bid": round(mid - half_spread + random.uniform(-0.01, 0.01), 4),
        "ask": round(mid + half_spread + random.uniform(-0.01, 0.01), 4),
        "mid": round(mid, 4),
        "last": round(mid + random.uniform(-0.02, 0.02), 4),
        "spot": None,
    }


def generate_commodity_tick():
    last = persistence.spots["XAUUSD"]
    spot = max(1.0, last["spot"] + random.uniform(-2.0, 2.0))
    return {
        "symbol": "XAUUSD", "asset_class": "COMMODITY", "currency": "USD",
        "bid": None, "ask": None, "mid": None,
        "last": round(spot, 4),
        "spot": round(spot, 4),
    }


def generate_futures_tick():
    last = persistence.spots["ES_FUT"]
    price = max(1.0, last["last"] + random.uniform(-5.0, 5.0))
    return {
        "symbol": "ES_FUT", "asset_class": "FUTURES", "currency": "USD",
        "bid": None, "ask": None, "mid": None,
        "last": round(price, 4),
        "spot": round(price, 4),
    }


def generate_fx_tick():
    last = persistence.spots["EURUSD"]
    spot = max(1.10, min(1.20, last["spot"] + random.uniform(-0.01, 0.01)))
    return {
        "symbol": "EURUSD", "asset_class": "FX", "currency": "USD",
        "bid": None, "ask": None, "mid": None, "last": None,
        "spot": round(spot, 4),
        "domestic_rate": last["domestic_rate"],
        "foreign_rate": last["foreign_rate"],
    }


def generate_curve_tick():
    rates = [round(anchor + random.uniform(-0.0008, 0.0008), 6) for anchor in persistence.CURVE_ANCHOR]
    return {
        "curve_name": "USD_GOV", "curve_type": "YIELD", "currency": "USD",
        "tenors": list(persistence.CURVE_TENORS),
        "rates": rates,
    }

GENERATORS = [
    ("market_tick", "spot",  "ACME",    generate_equity_tick),
    ("market_tick", "spot",  "XAUUSD",  generate_commodity_tick),
    ("market_tick", "spot",  "ES_FUT",  generate_futures_tick),
    ("market_tick", "spot",  "EURUSD",  generate_fx_tick),
    ("curve_tick",  "curve", "USD_GOV", generate_curve_tick),
]


def _run_generator(event_type, kind, key, build):
    while True:
        with persistence.data_lock:
            tick = build()
            tick["event_id"] = persistence.ticks_generated
            tick["event_time"] = get_iso_timestamp()
            persistence.ticks_generated += 1
            persistence.last_event_timestamp = tick["event_time"]
            persistence.update_state(kind, key, tick)

        persistence.persist(kind, tick)
        publish_tick(event_type, tick)

        time.sleep(TICK_INTERVAL_MS / 1000.0 * random.uniform(0.8, 1.2))


def start_generators():
    threads = []
    for event_type, kind, key, build in GENERATORS:
        thread = threading.Thread(
            target=_run_generator,
            args=(event_type, kind, key, build),
            name=f"gen-{key}",
            daemon=True,
        )
        thread.start()
        threads.append(thread)
    logging.info("Started %d market-data generators", len(threads))
    return threads
