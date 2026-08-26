"""Remove board/SSE rows when a provider-symbol leaves its serving universe."""

from app import quote_lifecycle, quote_store
from app.publisher import publish_removal
from shared.active_set import load_active_set


def cleanup_active_drops(provider, previous, fresh):
    candidates = [
        symbol
        for symbol, entry in previous.items()
        if entry.serves(provider)
        and (symbol not in fresh or not fresh[symbol].serves(provider))
    ]
    for symbol in candidates:
        with quote_lifecycle.locked_keys(symbol, (provider,)):
            current = load_active_set().get(symbol)
            if current is not None and current.serves(provider):
                continue
            quote_store.delete_board_rows(symbol, (provider,))
            publish_removal([{"provider": provider, "symbol": symbol}])


def cleanup_reference_drops(provider, symbols, current_universe):
    for symbol in sorted(symbols):
        with quote_lifecycle.locked_keys(symbol, (provider,)):
            if symbol in current_universe():
                continue
            quote_store.delete_board_rows(symbol, (provider,))
            publish_removal([{"provider": provider, "symbol": symbol}])
