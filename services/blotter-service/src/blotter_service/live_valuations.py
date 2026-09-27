"""Latest live valuation per trade, fed by the pricing valuation stream."""

import threading

from desk_domain.valuation_records import is_final, valued_at, with_decimals

_lock = threading.Lock()
_latest = {}


def replace_all(rows):
    live = {
        row["trade_id"]: with_decimals(row)
        for row in rows
        if row.get("trade_id") and not is_final(row)
    }
    with _lock:
        _latest.clear()
        _latest.update(live)


def record(valuation):
    trade_id = valuation.get("trade_id")
    if not trade_id:
        return
    with _lock:
        if is_final(valuation):
            _latest.pop(trade_id, None)
            return
        current_at = valued_at(_latest.get(trade_id) or {})
        incoming_at = valued_at(valuation)
        if current_at is not None and incoming_at is not None and incoming_at < current_at:
            return
        _latest[trade_id] = with_decimals(valuation)


def get(trade_id):
    with _lock:
        return _latest.get(trade_id)


def count():
    with _lock:
        return len(_latest)
