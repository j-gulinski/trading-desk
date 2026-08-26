import re
import uuid

from shared.models import WatchlistItem
from shared.providers import capable_providers

SPOT_ASSET_CLASSES = ("EQUITY", "FX", "COMMODITY")
CURVE_PRICED_ASSET_CLASSES = ("BOND", "IRS", "EUROPEAN_OPTION")
OPTION_UNDERLYING_ASSET_CLASSES = ("EQUITY",)
TRADE_QUANTITY_MIN = 1
TRADE_QUANTITY_MAX = 1_000_000
WHOLE_QUANTITY_ASSET_CLASSES = ("EQUITY", "EUROPEAN_OPTION")

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_.:\-]{1,31}$")


def is_valid_symbol(symbol):
    return isinstance(symbol, str) and SYMBOL_PATTERN.match(symbol) is not None


MODEL_CONTRACT_PREFIXES = {
    "BOND": "BOND",
    "IRS": "IRS",
    "EUROPEAN_OPTION": "OPT",
}


def model_contract_symbol(asset_class, trade_id):
    prefix = MODEL_CONTRACT_PREFIXES.get(asset_class)
    try:
        suffix = uuid.UUID(str(trade_id)).hex[:16].upper()
    except (ValueError, TypeError, AttributeError):
        return None
    return f"{prefix}-{suffix}" if prefix else None


def watchlist_items(session):
    return session.query(WatchlistItem).order_by(WatchlistItem.symbol).all()


def watched_providers(asset_class, providers):
    if providers is None:
        return frozenset(capable_providers(asset_class))
    return frozenset(name for name, chosen in providers.items() if chosen)


def watchlist_option_underlying_symbols(session):
    return [
        item.symbol
        for item in watchlist_items(session)
        if item.asset_class in OPTION_UNDERLYING_ASSET_CLASSES
    ]


def watchlist_spot_currencies(session):
    return {
        item.symbol: item.currency
        for item in watchlist_items(session)
        if item.asset_class in SPOT_ASSET_CLASSES
    }
