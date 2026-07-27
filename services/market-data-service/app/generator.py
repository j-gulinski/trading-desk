import random
import threading
import time
from decimal import Decimal

from app import persistence
from app.config import TICK_INTERVAL_MS, SERVICE_NAME
from app.publisher import publish_tick
from shared.functions import get_iso_timestamp
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)


PRICE_MODEL = {
    "ACME": {"field": "mid", "volatility": 0.00065},
    "XAUUSD": {"field": "spot", "volatility": 0.00050},
    "ES_FUT": {"field": "last", "volatility": 0.00045},
    "EURUSD": {"field": "spot", "volatility": 0.00025},
}
PRICE_MEAN_REVERSION = 0.02

CURVE_VOLATILITY = 0.000025
CURVE_MEAN_REVERSION = 0.08

INDEX_BASKET = {"ACME": "mid", "XAUUSD": "spot", "ES_FUT": "last"}
INDEX_BASE_LEVEL = float(persistence.spots["MARKET_INDEX"]["last"])
_INDEX_BASE_PRICES = {
    symbol: float(persistence.spots[symbol][field])
    for symbol, field in INDEX_BASKET.items()
}
_PRICE_ANCHORS = {
    symbol: float(persistence.spots[symbol][model["field"]])
    for symbol, model in PRICE_MODEL.items()
}


def _dec(value: float, places: int = 4) -> Decimal:
    return Decimal(str(round(value, places)))


def _round_to_tick(value: float, tick_size: float) -> float:
    return round(value / tick_size) * tick_size


def _next_price(symbol: str) -> float:
    model = PRICE_MODEL[symbol]
    field = model["field"]
    current = float(persistence.spots[symbol][field])
    anchor = _PRICE_ANCHORS[symbol]
    relative_gap = (anchor - current) / anchor
    relative_move = random.gauss(
        PRICE_MEAN_REVERSION * relative_gap,
        model["volatility"],
    )
    return max(0.00001, current * (1 + relative_move))


def generate_equity_tick():
    mid = _round_to_tick(_next_price("ACME"), 0.01)
    half_spread = 0.01
    return {
        "symbol": "ACME", "asset_class": "EQUITY", "currency": "USD",
        "bid": _dec(mid - half_spread, 2),
        "ask": _dec(mid + half_spread, 2),
        "mid": _dec(mid, 2),
        "last": _dec(mid, 2),
        "spot": None,
    }


def generate_commodity_tick():
    spot = _round_to_tick(_next_price("XAUUSD"), 0.10)
    return {
        "symbol": "XAUUSD", "asset_class": "COMMODITY", "currency": "USD",
        "bid": _dec(spot - 0.10, 2),
        "ask": _dec(spot + 0.10, 2),
        "mid": _dec(spot, 2),
        "last": _dec(spot, 2),
        "spot": _dec(spot, 2),
    }


def generate_futures_tick():
    price = _round_to_tick(_next_price("ES_FUT"), 0.25)
    return {
        "symbol": "ES_FUT", "asset_class": "FUTURES", "currency": "USD",
        "bid": _dec(price, 2),
        "ask": _dec(price + 0.25, 2),
        "mid": None,
        "last": _dec(price, 2),
        "spot": _dec(price, 2),
    }


def generate_fx_tick():
    last = persistence.spots["EURUSD"]
    spot = _round_to_tick(_next_price("EURUSD"), 0.00001)
    return {
        "symbol": "EURUSD", "asset_class": "FX", "currency": "USD",
        "bid": _dec(spot - 0.00004, 5),
        "ask": _dec(spot + 0.00004, 5),
        "mid": _dec(spot, 5),
        "last": None,
        "spot": _dec(spot, 5),
        "domestic_rate": last["domestic_rate"],
        "foreign_rate": last["foreign_rate"],
    }


def generate_index_tick():
    ratios = [
        float(persistence.spots[symbol][field]) / _INDEX_BASE_PRICES[symbol]
        for symbol, field in INDEX_BASKET.items()
    ]
    level = INDEX_BASE_LEVEL * sum(ratios) / len(ratios)
    return {
        "symbol": "MARKET_INDEX", "asset_class": "INDEX", "currency": "USD",
        "bid": None, "ask": None, "mid": None,
        "last": _dec(level, 2),
        "spot": _dec(level, 2),
    }


def generate_curve_tick():
    current_rates = [float(rate) for rate in persistence.curves["USD_GOV"]["rates"]]
    level_shock = random.gauss(0, CURVE_VOLATILITY)
    slope_shock = random.gauss(0, CURVE_VOLATILITY / 2)
    min_tenor = min(persistence.CURVE_TENORS)
    tenor_span = max(persistence.CURVE_TENORS) - min_tenor

    rates = []
    for tenor, current, anchor in zip(
        persistence.CURVE_TENORS,
        current_rates,
        persistence.CURVE_ANCHOR,
    ):
        slope_loading = 2 * (tenor - min_tenor) / tenor_span - 1
        next_rate = (
            current
            + CURVE_MEAN_REVERSION * (anchor - current)
            + level_shock
            + slope_loading * slope_shock
            + random.gauss(0, CURVE_VOLATILITY / 5)
        )
        rates.append(round(next_rate, 6))

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
    ("market_tick", "spot",  "MARKET_INDEX", generate_index_tick),
    ("curve_tick",  "curve", "USD_GOV", generate_curve_tick),
]


def _run_generator(event_type, kind, key, build):
    while True:
        with persistence.data_lock:
            tick = build()
            tick["stream_id"] = persistence.stream_id
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
