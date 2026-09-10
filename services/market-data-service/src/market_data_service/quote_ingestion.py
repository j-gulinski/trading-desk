from desk_domain.active_set import load_active_set
from desk_domain.quotes import wire_tick
from market_data_service import quote_lifecycle, quote_store
from market_data_service.providers.base import ProviderDataError
from market_data_service.publisher import publish_quote
from market_data_service.quote_audit import audit_quote_write


def store_and_publish(quote, classifier):
    provider, symbol = quote.provider, quote.symbol
    with quote_lifecycle.locked_keys(symbol, (provider,)):
        current = load_active_set().get(symbol)
        if current is None or not current.serves(provider):
            raise ProviderDataError(provider, f"{symbol} left the {provider} active set during refresh")
        changed, created, accepted = quote_store.store_quote(quote, classifier)
        if not accepted:
            raise ProviderDataError(provider, f"older observation for {symbol} ignored; current row retained")
        if changed:
            audit_quote_write(provider, quote, created)
        tick = wire_tick(quote, classifier, current.origin(provider))
        publish_quote(tick)
        return tick
