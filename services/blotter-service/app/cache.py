import threading
from collections import defaultdict
from datetime import datetime
from decimal import Decimal


class Trade:
    def __init__(self, trade_id, book_id, asset_class, symbol, side, status,
                 quantity, trade_price, currency, opened_at=None, closed_at=None,
                 close_price=None, close_reason=None, market_data_provider=None,
                 entry_price_timestamp=None, entry_snapshot_id=None,
                 close_price_timestamp=None, close_snapshot_id=None,
                 client_seen_price=None, source=None, created_by_service=None,
                 terms=None):
        self.trade_id = trade_id
        self.book_id = book_id
        self.asset_class = asset_class
        self.symbol = symbol
        self.side = side
        self.status = status
        self.quantity = quantity
        self.trade_price = trade_price
        self.currency = currency
        self.opened_at = opened_at
        self.closed_at = closed_at
        self.close_price = close_price
        self.close_reason = close_reason
        self.market_data_provider = market_data_provider
        self.entry_price_timestamp = entry_price_timestamp
        self.entry_snapshot_id = entry_snapshot_id
        self.close_price_timestamp = close_price_timestamp
        self.close_snapshot_id = close_snapshot_id
        self.client_seen_price = client_seen_price
        self.source = source
        self.created_by_service = created_by_service
        self.terms = terms


class IndexedStore:
    def __init__(self, indexed_fields):
        self._lock = threading.Lock()
        self._by_id = {}
        self._indexed_fields = tuple(indexed_fields)
        self._indexes = {f: defaultdict(set) for f in self._indexed_fields}

    def add(self, obj):
        with self._lock:
            self._add(obj)

    def replace_all(self, objs):
        with self._lock:
            self._by_id = {}
            self._indexes = {f: defaultdict(set) for f in self._indexed_fields}
            for obj in objs:
                self._add(obj)

    def remove(self, obj_id):
        with self._lock:
            self._remove(obj_id)

    def _add(self, obj):
        if obj.trade_id in self._by_id:
            self._remove(obj.trade_id)
        self._by_id[obj.trade_id] = obj
        for f in self._indexed_fields:
            self._indexes[f][getattr(obj, f)].add(obj.trade_id)

    def _remove(self, obj_id):
        obj = self._by_id.pop(obj_id, None)
        if obj is None:
            return
        for f in self._indexed_fields:
            idx = self._indexes[f]
            value = getattr(obj, f)
            idx[value].discard(obj_id)
            if not idx[value]:
                del idx[value]

    def get(self, obj_id):
        with self._lock:
            return self._by_id.get(obj_id)

    def update_field(self, obj_id, field, value):
        with self._lock:
            obj = self._by_id.get(obj_id)
            if obj is None or getattr(obj, field) == value:
                return False
            self._remove(obj_id)
            setattr(obj, field, value)
            self._add(obj)
            return True

    def __len__(self):
        with self._lock:
            return len(self._by_id)

    def query(self, **filters):
        filters = {f: v for f, v in filters.items() if v is not None}
        with self._lock:
            id_sets = []
            for f, v in filters.items():
                if f not in self._indexes:
                    raise KeyError(f"{f} is not indexed")
                id_sets.append(self._indexes[f].get(v, set()))

            if not id_sets:
                return list(self._by_id.values())
            id_sets.sort(key=len)
            result_ids = set(id_sets[0])
            for s in id_sets[1:]:
                result_ids &= s
            return [self._by_id[i] for i in result_ids]

trades = IndexedStore(["book_id", "asset_class", "status", "symbol"])

reconciliation_lock = threading.RLock()
_val_lock = threading.Lock()
valuations = {}

_NUMERIC_FIELDS = ("fair_value", "market_value", "unrealized_pnl", "realized_pnl", "total_pnl")


def _parsed_valuation(valuation):
    parsed = dict(valuation)
    for field in _NUMERIC_FIELDS:
        if parsed.get(field) is not None:
            parsed[field] = Decimal(str(parsed[field]))
    return parsed


def _valued_at(valuation):
    try:
        return datetime.fromisoformat(str(valuation.get("valuation_time")))
    except (TypeError, ValueError):
        return None


def record_valuation(valuation):
    trade_id = valuation.get("trade_id")
    if trade_id is None:
        return False
    parsed = _parsed_valuation(valuation)
    with _val_lock:
        current = valuations.get(trade_id)
        current_at = _valued_at(current or {})
        incoming_at = _valued_at(parsed)
        if current_at is not None and incoming_at is not None and incoming_at < current_at:
            return False
        valuations[trade_id] = parsed
    return True


def replace_valuations(rows, active_trade_ids):
    replacement = {
        row["trade_id"]: _parsed_valuation(row)
        for row in rows
        if row.get("trade_id") in active_trade_ids
        and not bool((row.get("valuation_payload") or {}).get("final"))
    }
    global valuations
    with _val_lock:
        valuations = replacement


def get_valuation(trade_id):
    with _val_lock:
        return valuations.get(trade_id)


def drop_valuation(trade_id):
    with _val_lock:
        valuations.pop(trade_id, None)
