import re

from shared.models import WatchlistItem
from shared.providers import capable_providers

SPOT_ASSET_CLASSES = ("EQUITY", "FX", "COMMODITY")
CURVE_PRICED_ASSET_CLASSES = ("BOND", "IRS", "EUROPEAN_OPTION")

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_.\-]{1,31}$")


def is_valid_symbol(symbol):
    return isinstance(symbol, str) and SYMBOL_PATTERN.match(symbol) is not None


def watchlist_items(session):
    return session.query(WatchlistItem).order_by(WatchlistItem.symbol).all()


def watched_providers(asset_class, providers):
    if providers is None:
        return frozenset(capable_providers(asset_class))
    return frozenset(name for name, chosen in providers.items() if chosen)


def watchlist_spot_symbols(session):
    return [
        item.symbol
        for item in watchlist_items(session)
        if item.asset_class in SPOT_ASSET_CLASSES
    ]


def watchlist_spot_currencies(session):
    return {
        item.symbol: item.currency
        for item in watchlist_items(session)
        if item.asset_class in SPOT_ASSET_CLASSES
    }
