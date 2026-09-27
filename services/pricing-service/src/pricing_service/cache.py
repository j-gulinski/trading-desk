"""Thread-safe in-memory state for the pricing process."""

import threading
from decimal import Decimal

from pricing_service.config import SERVICE_NAME
from desk_runtime.logging_config import get_logger
from desk_domain.quotes import as_decimal
from desk_domain.valuation_records import is_final, valued_at
from desk_domain.instruments import instrument_for

log = get_logger(SERVICE_NAME)

data_lock = threading.Lock()

ticks_received = 0
last_event_timestamp = None
market_data_connection = "DISCONNECTED"

# Live state belongs here; durable data access belongs in repository.py.
# Spot quotes are keyed by (provider, symbol), while curves use the stable curve name.
spots = {}
curves = {}
active_trades = {}
trades_by_quote = {}
trades_by_curve = {}
last_written_at = {}
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
    replacement_spots = {
        (row["provider"], row["symbol"]): _parsed_spot(row) for row in snapshot_spots.values()
    }
    replacement_curves = {row["curve_name"]: row for row in snapshot_curves.values()}
    global spots, curves
    with data_lock:
        spots = replacement_spots
        curves = replacement_curves


def drop_spots(rows):
    with data_lock:
        for row in rows:
            spots.pop((row.get("provider"), row.get("symbol")), None)


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


def _index(trades):
    by_quote, by_curve = {}, {}
    for trade in trades.values():
        try:
            instrument = instrument_for(trade["asset_class"], trade["symbol"], trade["metadata"])
        except (TypeError, ValueError):
            log.warning("trade_not_indexed", trade_id=trade["trade_id"])
            continue
        if instrument.needs_quote:
            key = (trade["market_data_provider"], instrument.quote_symbol)
            by_quote.setdefault(key, []).append(trade["trade_id"])
        if instrument.uses_curve():
            by_curve.setdefault(instrument.discount_curve, []).append(trade["trade_id"])
    return by_quote, by_curve


def _set_active_trades(trades):
    global active_trades, trades_by_quote, trades_by_curve
    active_trades = trades
    trades_by_quote, trades_by_curve = _index(trades)


def trades_for_quote(provider, symbol):
    with data_lock:
        return [active_trades[trade_id] for trade_id in trades_by_quote.get((provider, symbol), ())]


def trades_for_curve(curve_name):
    with data_lock:
        return [active_trades[trade_id] for trade_id in trades_by_curve.get(curve_name, ())]


def replace_active_trades(fresh):
    """Replace the active set and return (new or materially changed trades, first load)."""
    global _active_set_seeded
    with data_lock:
        entered_ids = fresh.keys() - active_trades.keys()
        changed_ids = {
            trade_id
            for trade_id in fresh.keys() & active_trades.keys()
            if fresh[trade_id] != active_trades[trade_id]
        }
        first_load = not _active_set_seeded
        _set_active_trades(fresh)
        _active_set_seeded = True
    dirty_ids = entered_ids | changed_ids
    return [fresh[trade_id] for trade_id in dirty_ids], first_load


def active_trades_snapshot():
    with data_lock:
        return list(active_trades.values())


def remove_active_trades(trade_ids):
    with data_lock:
        removed = set(trade_ids)
        _set_active_trades({
            trade_id: trade for trade_id, trade in active_trades.items()
            if trade_id not in removed
        })


def claim_valuation_write(trade_id, now, interval_seconds):
    with data_lock:
        last = last_written_at.get(trade_id)
        if last is not None and (now - last).total_seconds() < interval_seconds:
            return False
        last_written_at[trade_id] = now
        return True


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


def record_valuation(valuation):
    """Keep a final close valuation from being overwritten by a stale live batch."""
    with data_lock:
        existing = latest_valuations.get(valuation["trade_id"])
        if existing is not None and is_final(existing) and not is_final(valuation):
            return False
        if existing is not None and is_final(existing) == is_final(valuation):
            existing_at = valued_at(existing)
            incoming_at = valued_at(valuation)
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
