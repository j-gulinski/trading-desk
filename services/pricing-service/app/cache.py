"""Thread-safe in-memory state for the pricing process."""

import datetime
import threading
from decimal import Decimal

from app.config import SERVICE_NAME
from shared.config import DEFAULT_QUOTE_PROVIDER
from shared.logging_config import get_logger
from shared.quotes import as_decimal
from shared.symbols import SPOT_ASSET_CLASSES

log = get_logger(SERVICE_NAME)

data_lock = threading.Lock()
clients_lock = threading.Lock()

ticks_received = 0
last_event_timestamp = None
market_data_connection = "DISCONNECTED"
client_event_queues = set()

# Live state belongs here; durable data access belongs in repository.py.
# Spot quotes are keyed by (provider, symbol), while curves use the stable curve name.
spots = {}
curves = {}
active_trades = {}
latest_valuations = {}
book_risk_metrics = {}
_active_set_seeded = False

SPOT_PRICE_FIELDS = ("bid", "ask", "last", "mid")

# Market data state


def _parsed_spot(tick):
    return {
        **tick,
        **{field: as_decimal(tick.get(field)) for field in SPOT_PRICE_FIELDS},
    }


def _revision(row, primary):
    return (str(row.get(primary) or ""), str(row.get("received_at") or ""))


def update_spot(tick):
    parsed = _parsed_spot(tick)
    with data_lock:
        key = (tick["provider"], tick["symbol"])
        current = spots.get(key)
        if current is not None and _revision(parsed, "provider_timestamp") \
                <= _revision(current, "provider_timestamp"):
            return False
        spots[key] = parsed
        return True


def update_curve(tick):
    with data_lock:
        key = tick["curve_name"]
        current = curves.get(key)
        if current is not None and _revision(tick, "as_of_date") \
                <= _revision(current, "as_of_date"):
            return False
        curves[key] = tick
        return True


def replace_market_state(snapshot_spots, snapshot_curves):
    """Atomically reconcile the live market cache to one server snapshot.

    Building the replacement maps before taking the lock means a malformed snapshot
    cannot leave the process with a half-replaced market state.
    """
    replacement_spots = {}
    for row in (snapshot_spots or {}).values():
        parsed = _parsed_spot(row)
        key = (row["provider"], row["symbol"])
        current = replacement_spots.get(key)
        if current is None or _revision(parsed, "provider_timestamp") \
                > _revision(current, "provider_timestamp"):
            replacement_spots[key] = parsed

    replacement_curves = {}
    for row in (snapshot_curves or {}).values():
        key = row["curve_name"]
        current = replacement_curves.get(key)
        if current is None or _revision(row, "as_of_date") \
                > _revision(current, "as_of_date"):
            replacement_curves[key] = row

    global spots, curves
    with data_lock:
        spots = replacement_spots
        curves = replacement_curves


def get_spot(provider, symbol):
    with data_lock:
        return spots.get((provider, symbol))


def drop_spots(rows):
    with data_lock:
        for row in rows:
            spots.pop((row.get("provider"), row.get("symbol")), None)


def get_curve(name):
    with data_lock:
        return curves.get(name)


def record_market_event(event_time):
    global ticks_received, last_event_timestamp
    with data_lock:
        ticks_received += 1
        last_event_timestamp = event_time


def set_market_data_connection(state):
    global market_data_connection
    with data_lock:
        changed = market_data_connection != state
        market_data_connection = state
    return changed


def health_snapshot():
    with data_lock:
        return {
            "market_data_connection": market_data_connection,
            "received_events": ticks_received,
            "active_trades": len(active_trades),
            "last_market_event_time": last_event_timestamp,
        }


# Active trade state and market-data routing


def trade_provider(trade):
    provider = trade.get("market_data_provider")
    if provider:
        return provider
    log.warning(
        "trade_provider_defaulted",
        trade_id=trade.get("trade_id"),
        symbol=trade.get("symbol"),
        provider=DEFAULT_QUOTE_PROVIDER,
    )
    return DEFAULT_QUOTE_PROVIDER


def needs_spot(trade):
    return (
        trade["asset_class"] in SPOT_ASSET_CLASSES
        or trade["asset_class"] == "EUROPEAN_OPTION"
    )


def trades_for_quote(provider, symbol):
    with data_lock:
        return [
            trade
            for trade in active_trades.values()
            if needs_spot(trade)
            and trade_provider(trade) == provider
            and (
                trade["symbol"] == symbol
                or (trade.get("metadata") or {}).get("underlying_symbol") == symbol
            )
        ]


def _trade_curves(trade):
    metadata = trade.get("metadata") or {}
    return {
        name
        for name in (
            metadata.get("discount_curve"),
            metadata.get("projection_curve"),
            metadata.get("curve"),
        )
        if name
    }


def trades_for_curve(curve_name):
    with data_lock:
        return [
            trade
            for trade in active_trades.values()
            if curve_name in _trade_curves(trade)
        ]


def replace_active_trades(fresh):
    """Replace the active set and return (new or materially changed trades, first load)."""
    global active_trades, _active_set_seeded
    with data_lock:
        entered_ids = fresh.keys() - active_trades.keys()
        changed_ids = {
            trade_id
            for trade_id in fresh.keys() & active_trades.keys()
            if fresh[trade_id] != active_trades[trade_id]
        }
        first_load = not _active_set_seeded
        active_trades = fresh
        _active_set_seeded = True
    dirty_ids = entered_ids | changed_ids
    return [fresh[trade_id] for trade_id in dirty_ids], first_load


def active_trades_snapshot():
    with data_lock:
        return list(active_trades.values())


def remove_active_trades(trade_ids):
    with data_lock:
        for trade_id in trade_ids:
            active_trades.pop(trade_id, None)


# Latest valuation and book-risk state


def book_pnl_snapshot():
    """Latest cumulative PnL per book, including terminal realized valuations."""
    totals = {}
    with data_lock:
        for valuation in latest_valuations.values():
            book_id = valuation.get("book_id")
            if book_id is None:
                continue
            entry = totals.setdefault(
                book_id,
                {
                    "book_id": book_id,
                    "book_name": valuation.get("book_name"),
                    "pnl": Decimal("0"),
                },
            )
            entry["pnl"] += Decimal(str(valuation.get("total_pnl") or 0))
    return totals


def set_book_risk(metrics):
    with data_lock:
        book_risk_metrics[metrics["book_id"]] = metrics


def all_book_risk():
    with data_lock:
        return list(book_risk_metrics.values())


def _is_final(valuation):
    return bool((valuation.get("valuation_payload") or {}).get("final"))


def _valuation_time(valuation):
    try:
        return datetime.datetime.fromisoformat(str(valuation.get("valuation_time")))
    except (TypeError, ValueError):
        return None


def record_valuation(valuation):
    """Keep a final close valuation from being overwritten by a stale live batch."""
    with data_lock:
        existing = latest_valuations.get(valuation["trade_id"])
        if existing is not None and _is_final(existing) and not _is_final(valuation):
            return False
        if existing is not None and _is_final(existing) == _is_final(valuation):
            existing_at = _valuation_time(existing)
            incoming_at = _valuation_time(valuation)
            if (
                existing_at is not None
                and incoming_at is not None
                and incoming_at < existing_at
            ):
                return False
        latest_valuations[valuation["trade_id"]] = valuation
        return True


def is_current_valuation(valuation):
    with data_lock:
        return latest_valuations.get(valuation["trade_id"]) is valuation


def all_valuations():
    with data_lock:
        return list(latest_valuations.values())


def get_valuation(trade_id):
    with data_lock:
        return latest_valuations.get(trade_id)
