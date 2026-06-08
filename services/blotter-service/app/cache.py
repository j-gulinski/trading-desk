import threading
from collections import defaultdict
from decimal import Decimal


class Trade:
    def __init__(self, trade_id, book_id, asset_class, symbol, side, status,
                 quantity, trade_price, currency, opened_at=None, closed_at=None,
                 close_price=None, close_reason=None):
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


class IndexedStore:
    def __init__(self, indexed_fields):
        self._lock = threading.Lock()
        self._by_id = {}
        self._indexed_fields = tuple(indexed_fields)
        self._indexes = {f: defaultdict(set) for f in self._indexed_fields}

    def add(self, obj):
        with self._lock:
            self._add(obj)

    def add_many(self, objs):
        with self._lock:
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

_val_lock = threading.Lock()
valuations = {}

_NUMERIC_FIELDS = ("fair_value", "market_value", "unrealized_pnl", "realized_pnl", "total_pnl")


def record_valuation(valuation):
    trade_id = valuation.get("trade_id")
    if trade_id is None:
        return
    parsed = dict(valuation)
    for f in _NUMERIC_FIELDS:
        if parsed.get(f) is not None:
            parsed[f] = Decimal(str(parsed[f]))
    with _val_lock:
        valuations[trade_id] = parsed


def get_valuation(trade_id):
    with _val_lock:
        return valuations.get(trade_id)


def drop_valuation(trade_id):
    with _val_lock:
        valuations.pop(trade_id, None)
