from dataclasses import dataclass

from shared.config import BENCHMARK_PROVIDER, BENCHMARK_SYMBOL, DEFAULT_QUOTE_PROVIDER
from shared.db import session_scope
from shared.models import Trade
from shared.providers import supports_quotes
from shared.symbols import watched_providers, watchlist_items

EMPTY = frozenset()


@dataclass(frozen=True)
class ActiveSymbol:
    symbol: str
    asset_class: str
    currency: str
    tier: int
    watched_by: frozenset = EMPTY
    held_by: frozenset = EMPTY
    benchmark_by: frozenset = EMPTY

    @property
    def providers(self):
        return self.watched_by | self.held_by | self.benchmark_by

    @property
    def tradeable(self):
        return bool(self.watched_by or self.held_by)

    def serves(self, provider):
        return provider in self.providers and supports_quotes(provider, self.asset_class)

    def origin(self, provider):
        return {
            "watched": provider in self.watched_by,
            "held": provider in self.held_by,
            "benchmark": provider in self.benchmark_by,
        }


def _read(session):
    watched = [
        (item.symbol, item.asset_class, item.currency,
         watched_providers(item.asset_class, item.providers))
        for item in watchlist_items(session)
    ]
    open_rows = (
        session.query(Trade.symbol, Trade.asset_class, Trade.trade_currency,
                      Trade.market_data_provider)
        .filter(Trade.status == "ACTIVE")
        .distinct()
        .all()
    )
    return watched, open_rows


def load_active_set(session=None):
    if session is None:
        with session_scope() as owned:
            watched, open_rows = _read(owned)
    else:
        watched, open_rows = _read(session)

    held = {}
    holders = {}
    for symbol, asset_class, currency, provider in open_rows:
        held[symbol] = (asset_class, currency)
        holders.setdefault(symbol, set()).add(provider or DEFAULT_QUOTE_PROVIDER)

    entries = {}
    for symbol, (asset_class, currency) in held.items():
        entries[symbol] = ActiveSymbol(
            symbol, asset_class, currency, 1,
            held_by=frozenset(holders[symbol]),
        )
    for symbol, asset_class, currency, chosen in watched:
        current = entries.get(symbol)
        entries[symbol] = ActiveSymbol(
            symbol, asset_class, currency,
            1 if current is not None or symbol == BENCHMARK_SYMBOL else 2,
            watched_by=chosen,
            held_by=current.held_by if current else EMPTY,
        )

    benchmark = entries.get(BENCHMARK_SYMBOL)
    entries[BENCHMARK_SYMBOL] = ActiveSymbol(
        BENCHMARK_SYMBOL,
        benchmark.asset_class if benchmark else "EQUITY",
        benchmark.currency if benchmark else "USD",
        1,
        watched_by=benchmark.watched_by if benchmark else EMPTY,
        held_by=benchmark.held_by if benchmark else EMPTY,
        benchmark_by=frozenset({BENCHMARK_PROVIDER}),
    )
    return entries
