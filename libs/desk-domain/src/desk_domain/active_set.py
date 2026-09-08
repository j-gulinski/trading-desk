from dataclasses import dataclass

from desk_runtime.config import BENCHMARK_PROVIDER, BENCHMARK_SYMBOL, DEFAULT_QUOTE_PROVIDER
from desk_runtime.db import session_scope
from desk_domain.models import Instrument, Trade
from sqlalchemy.orm import aliased
from desk_domain.providers import supports_quotes
from desk_domain.symbols import watched_providers, watchlist_items

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
    retired: bool = False

    @property
    def providers(self):
        return self.watched_by | self.held_by | self.benchmark_by

    @property
    def tradeable(self):
        """Whether the symbol may be used for a new trade.

        A held-only symbol remains pollable so its open position can be valued, but
        removing it from the watchlist removes it from the new-trade catalog.
        """
        return bool(self.watched_by) and not self.retired

    def serves_open(self, provider):
        return self.tradeable and provider in self.watched_by and supports_quotes(provider, self.asset_class)

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
         watched_providers(item.asset_class, item.providers), item.retired_at is not None)
        for item in watchlist_items(session)
    ]
    underlying = aliased(Instrument)
    open_rows = (
        session.query(Instrument.symbol, Instrument.asset_class, Instrument.currency,
                      Trade.market_data_provider, underlying.symbol,
                      underlying.asset_class, underlying.currency)
        .join(Instrument, Trade.instrument_id == Instrument.instrument_id)
        .outerjoin(underlying, Instrument.underlying_instrument_id == underlying.instrument_id)
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
    for symbol, asset_class, currency, provider, underlying, underlying_class, underlying_currency in open_rows:
        if asset_class == "EUROPEAN_OPTION":
            symbol, asset_class, currency = underlying, underlying_class, underlying_currency
        elif asset_class in ("BOND", "IRS"):
            continue
        held[symbol] = (asset_class, currency)
        holders.setdefault(symbol, set()).add(provider or DEFAULT_QUOTE_PROVIDER)

    entries = {}
    for symbol, (asset_class, currency) in held.items():
        entries[symbol] = ActiveSymbol(
            symbol, asset_class, currency, 1,
            held_by=frozenset(holders[symbol]),
        )
    for symbol, asset_class, currency, chosen, retired in watched:
        current = entries.get(symbol)
        entries[symbol] = ActiveSymbol(
            symbol, asset_class, currency,
            1 if current is not None or symbol == BENCHMARK_SYMBOL else 2,
            watched_by=chosen,
            held_by=current.held_by if current else EMPTY,
            retired=retired,
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
        retired=benchmark.retired if benchmark else False,
    )
    return entries
