import uuid
import datetime
import threading

from shared.functions import utcnow
from shared.db import session_scope
from shared.audit import write_audit
from shared.logging_config import get_logger
from shared.models import MarketDataSpotPrice, MarketDataCurve, MarketDataSnapshot
from app.config import SERVICE_NAME

log = get_logger(SERVICE_NAME)

data_lock = threading.Lock()
stream_id = str(uuid.uuid4())
ticks_generated = 0
last_event_timestamp = None

spots = {
    "ACME": {
        "symbol": "ACME", "asset_class": "EQUITY", "currency": "USD",
        "bid": 100.94, "ask": 100.96, "mid": 100.95, "last": 100.95, "spot": None,
    },
    "XAUUSD": {
        "symbol": "XAUUSD", "asset_class": "COMMODITY", "currency": "USD",
        "bid": 2453.50, "ask": 2453.70, "mid": 2453.60, "last": 2453.60, "spot": 2453.60,
    },
    "ES_FUT": {
        "symbol": "ES_FUT", "asset_class": "FUTURES", "currency": "USD",
        "bid": 5250.25, "ask": 5250.50, "mid": None, "last": 5250.25, "spot": 5250.25,
    },
    "EURUSD": {
        "symbol": "EURUSD", "asset_class": "FX", "currency": "USD",
        "bid": 1.09196, "ask": 1.09204, "mid": 1.09200, "last": None, "spot": 1.09200,
        "domestic_rate": 0.0430, "foreign_rate": 0.0275,
    },
    "MARKET_INDEX": {
        "symbol": "MARKET_INDEX", "asset_class": "INDEX", "currency": "USD",
        "bid": None, "ask": None, "mid": None, "last": 4883.11, "spot": 4883.11,
    },
}

CURVE_TENORS = [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
CURVE_ANCHOR = [0.0450, 0.0443, 0.0431, 0.0422, 0.0412, 0.0410, 0.0415]

curves = {
    "USD_GOV": {"curve_name": "USD_GOV", "curve_type": "YIELD", "currency": "USD",
                "tenors": list(CURVE_TENORS), "rates": list(CURVE_ANCHOR)},
}

def update_state(kind: str, key: str, tick: dict) -> None:
    if kind == "curve":
        curves[key] = tick
    else:
        spots[key] = tick


def current_snapshot() -> dict:
    with data_lock:
        return {
            "stream_id": stream_id,
            "event_id": ticks_generated - 1 if ticks_generated else None,
            "spots": {key: dict(value) for key, value in spots.items()},
            "curves": {key: dict(value) for key, value in curves.items()},
        }


def persist(kind: str, tick: dict) -> None:
    try:
        if kind == "curve":
            _save_curve(tick)
        else:
            _save_spot(tick)
    except Exception:
        log.exception("persist_failed", kind=kind)
        write_audit(SERVICE_NAME, "DB_WRITE_ERROR", "Failed to persist market data event",
                    entity_type="MARKET_DATA", severity="ERROR")


def _event_time(tick: dict) -> datetime.datetime:
    try:
        return datetime.datetime.fromisoformat(tick["event_time"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return utcnow()


def _save_spot(tick: dict) -> None:
    created_at = utcnow()
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
            event_time=_event_time(tick),
            created_at=created_at,
            raw_payload=tick,
        ))


def _save_curve(tick: dict) -> None:
    created_at = utcnow()
    with session_scope() as session:
        session.add(MarketDataCurve(
            curve_id=uuid.uuid4(),
            event_id=tick.get("event_id"),
            curve_name=tick["curve_name"],
            curve_type=tick["curve_type"],
            currency=tick.get("currency"),
            tenors=tick["tenors"],
            rates=tick["rates"],
            event_time=_event_time(tick),
            created_at=created_at,
            raw_payload=tick,
        ))


def save_snapshot() -> None:
    payload = current_snapshot()
    try:
        with session_scope() as session:
            session.add(MarketDataSnapshot(
                snapshot_id=uuid.uuid4(),
                event_id=payload["event_id"],
                snapshot_type="FULL",
                snapshot_time=utcnow(),
                created_at=utcnow(),
                payload=payload,
            ))
            write_audit(SERVICE_NAME, "SNAPSHOT_WRITTEN", "Market data snapshot persisted",
                        entity_type="MARKET_DATA",
                        payload={"event_id": payload["event_id"]}, session=session)
    except Exception:
        log.exception("snapshot_persist_failed")
        write_audit(SERVICE_NAME, "DB_WRITE_ERROR", "Failed to persist snapshot",
                    entity_type="MARKET_DATA", severity="ERROR")
