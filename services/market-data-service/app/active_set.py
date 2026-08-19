from dataclasses import dataclass

from shared.config import BENCHMARK_SYMBOL
from shared.db import session_scope
from shared.models import Trade
from shared.symbols import watchlist_items


@dataclass(frozen=True)
class ActiveSymbol:
    symbol: str
    asset_class: str
    currency: str
    tier: int


def load_active_set():
    with session_scope() as session:
        watched = [
            (item.symbol, item.asset_class, item.currency)
            for item in watchlist_items(session)
        ]
        open_rows = (
            session.query(Trade.symbol, Trade.asset_class, Trade.trade_currency)
            .filter(Trade.status == "ACTIVE")
            .distinct()
            .all()
        )
    entries = {
        symbol: ActiveSymbol(symbol, asset_class, currency, 1)
        for symbol, asset_class, currency in open_rows
    }
    open_symbols = set(entries)
    for symbol, asset_class, currency in watched:
        tier = 1 if symbol in open_symbols or symbol == BENCHMARK_SYMBOL else 2
        entries[symbol] = ActiveSymbol(symbol, asset_class, currency, tier)
    entries.setdefault(BENCHMARK_SYMBOL, ActiveSymbol(BENCHMARK_SYMBOL, "EQUITY", "USD", 1))
    return entries
