import time
import random
import threading
from decimal import Decimal

from app import persistence
from app.config import TICK_INTERVAL_MS, SERVICE_NAME
from app.publisher import publish_tick
from shared.functions import get_iso_timestamp
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)


VOL = 0.0002
CURVE_VOL = 0.00005


def _dec(value: float, places: int = 4) -> Decimal:
    return Decimal(str(round(value, places)))


def generate_equity_tick():
    mid = max(1.0, float(persistence.spots["ACME"]["mid"]) * (1 + random.uniform(-VOL, VOL)))
    half_spread = mid * 0.0005
    return {
        "symbol": "ACME", "asset_class": "EQUITY", "currency": "USD",
        "bid": _dec(mid - half_spread),
        "ask": _dec(mid + half_spread),
        "mid": _dec(mid),
        "last": _dec(mid),
        "spot": None,
    }


def generate_commodity_tick():
    spot = max(1.0, float(persistence.spots["XAUUSD"]["spot"]) * (1 + random.uniform(-VOL, VOL)))
    return {
        "symbol": "XAUUSD", "asset_class": "COMMODITY", "currency": "USD",
        "bid": None, "ask": None, "mid": None,
        "last": _dec(spot),
        "spot": _dec(spot),
    }


def generate_futures_tick():
    price = max(1.0, float(persistence.spots["ES_FUT"]["last"]) * (1 + random.uniform(-VOL, VOL)))
    return {
        "symbol": "ES_FUT", "asset_class": "FUTURES", "currency": "USD",
        "bid": None, "ask": None, "mid": None,
        "last": _dec(price),
        "spot": _dec(price),
    }


def generate_fx_tick():
    last = persistence.spots["EURUSD"]
    spot = float(last["spot"]) * (1 + random.uniform(-VOL, VOL))
    return {
        "symbol": "EURUSD", "asset_class": "FX", "currency": "USD",
        "bid": None, "ask": None, "mid": None, "last": None,
        "spot": _dec(spot, 6),
        "domestic_rate": last["domestic_rate"],
        "foreign_rate": last["foreign_rate"],
    }


def generate_curve_tick():
    rates = [round(anchor + random.uniform(-CURVE_VOL, CURVE_VOL), 6) for anchor in persistence.CURVE_ANCHOR]
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
    log.info("generators_started", count=len(threads))
    return threads
