import uuid
import logging
import datetime
import threading

from shared.functions import utcnow
from shared.db import session_scope
from shared.models import MarketDataSpotPrice, MarketDataCurve, MarketDataSnapshot

data_lock = threading.Lock()
ticks_generated = 0
last_event_timestamp = None

spots = {
    "ACME":   {"symbol": "ACME",   "asset_class": "EQUITY",    "currency": "USD",
               "bid": 99.95, "ask": 100.05, "mid": 100.00, "last": 100.00, "spot": None},
    "XAUUSD": {"symbol": "XAUUSD", "asset_class": "COMMODITY", "curdockerrency": "USD",
               "bid": None, "ask": None, "mid": None, "last": 2000.00, "spot": 2000.00},
    "ES_FUT": {"symbol": "ES_FUT", "asset_class": "FUTURES",   "currency": "USD",
               "bid": None, "ask": None, "mid": None, "last": 5000.00, "spot": 5000.00},
    "EURUSD": {"symbol": "EURUSD", "asset_class": "FX",        "currency": "USD",
               "bid": None, "ask": None, "mid": None, "last": None, "spot": 1.16,
               "domestic_rate": 0.0375, "foreign_rate": 0.0215},
}

CURVE_TENORS = [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
CURVE_ANCHOR = [0.030, 0.035, 0.038, 0.040, 0.043, 0.045, 0.047]

curves = {
    "USD_GOV": {"curve_name": "USD_GOV", "curve_type": "YIELD", "currency": "USD",
                "tenors": list(CURVE_TENORS), "rates": list(CURVE_ANCHOR)},
}

def update_state(kind: str, key: str, tick: dict) -> None:
    if kind == "curve":
        curves[key] = tick
    else:
        spots[key] = tick


def persist(kind: str, tick: dict) -> None:
    try:
        if kind == "curve":
            _save_curve(tick)
        else:
            _save_spot(tick)
    except Exception:
        logging.exception("Failed to persist market data event")


def _save_spot(tick: dict) -> None:
    with session_scope() as session:
        session.add(MarketDataSpotPrice(
            market_data_id=uuid.uuid4(),
            event_id=tick.get("event_id"),
            symbol=tick["symbol"],
            asset_class=tick["asset_class"],
            bid=tick.get("bid"),
            ask=tick.get("ask"),
            mid=tick.get("mid"),
            last=tick.get("last"),
            spot=tick.get("spot"),
            currency=tick.get("currency"),
            source="SIMULATED",
            event_time=utcnow(),
            created_at=utcnow(),
            raw_payload=tick,
        ))


def _save_curve(tick: dict) -> None:
    with session_scope() as session:
        session.add(MarketDataCurve(
            curve_id=uuid.uuid4(),
            event_id=tick.get("event_id"),
            curve_name=tick["curve_name"],
            curve_type=tick["curve_type"],
            currency=tick.get("currency"),
            tenors=tick["tenors"],
            rates=tick["rates"],
            event_time=utcnow(),
            created_at=utcnow(),
            raw_payload=tick,
        ))


def save_snapshot() -> None:
    with data_lock:
        payload = {
            "spots": {k: dict(v) for k, v in spots.items()},
            "curves": {k: dict(v) for k, v in curves.items()},
        }
        event_id = ticks_generated
    try:
        with session_scope() as session:
            session.add(MarketDataSnapshot(
                snapshot_id=uuid.uuid4(),
                event_id=event_id,
                snapshot_type="FULL",
                snapshot_time=utcnow(),
                created_at=utcnow(),
                payload=payload,
            ))
    except Exception:
        logging.exception("Failed to persist market data snapshot")
