import re
import uuid

from desk_domain.instruments import INSTRUMENT_TYPES
from desk_domain.models import Instrument, WatchlistItem
from desk_domain.providers import capable_providers

SPOT_ASSET_CLASSES = tuple(
    asset_class for asset_class, kind in INSTRUMENT_TYPES.items() if kind.symbol_prefix is None
)
CURVE_PRICED_ASSET_CLASSES = tuple(
    asset_class for asset_class, kind in INSTRUMENT_TYPES.items() if kind.needs_curve
)
TRADE_QUANTITY_MIN = 1
TRADE_QUANTITY_MAX = 1_000_000

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_.:\-]{1,31}$")


def is_valid_symbol(symbol):
    return isinstance(symbol, str) and SYMBOL_PATTERN.match(symbol) is not None


def model_contract_symbol(instrument, trade_id):
    try:
        suffix = uuid.UUID(str(trade_id)).hex[:16].upper()
    except (ValueError, TypeError, AttributeError):
        return None
    return f"{instrument.symbol_prefix}-{suffix}" if instrument.symbol_prefix else None


def watchlist_items(session):
    return (
        session.query(Instrument.instrument_id, Instrument.symbol, Instrument.name,
                      Instrument.asset_class, Instrument.currency, Instrument.market,
                      Instrument.retired_at, WatchlistItem.providers, WatchlistItem.created_at)
        .join(WatchlistItem, WatchlistItem.instrument_id == Instrument.instrument_id)
        .order_by(Instrument.symbol).all()
    )


def watched_providers(asset_class, providers):
    if providers is None:
        return frozenset(capable_providers(asset_class))
    return frozenset(name for name, chosen in providers.items() if chosen)


def watchlist_spot_catalog(session):
    """Watched, non-retired quote-priced instruments: the choices a model contract may
    reference as its underlying, with the currency each one trades in."""
    return {
        item.symbol: {"asset_class": item.asset_class, "currency": item.currency}
        for item in watchlist_items(session)
        if item.asset_class in SPOT_ASSET_CLASSES and item.retired_at is None
    }
