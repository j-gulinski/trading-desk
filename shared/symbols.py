import re

from shared.models import WatchlistItem

SPOT_ASSET_CLASSES = ("EQUITY", "FX", "COMMODITY")
CURVE_PRICED_ASSET_CLASSES = ("BOND", "IRS", "EUROPEAN_OPTION")

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_.\-]{1,31}$")


def is_valid_symbol(symbol):
    return isinstance(symbol, str) and SYMBOL_PATTERN.match(symbol) is not None


def watchlist_item(session, symbol):
    return session.get(WatchlistItem, symbol)


def watchlist_items(session):
    return session.query(WatchlistItem).order_by(WatchlistItem.symbol).all()


def watchlist_spot_symbols(session):
    return [
        item.symbol
        for item in watchlist_items(session)
        if item.asset_class in SPOT_ASSET_CLASSES
    ]
