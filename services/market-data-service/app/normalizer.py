from datetime import datetime, timezone

from app.clients.base import ProviderDataError
from shared.providers import FINNHUB, quote_grade
from shared.quotes import build_quote


def normalize_finnhub_quote(symbol, asset_class, currency, payload, received_at):
    last = payload.get("c") if isinstance(payload, dict) else None
    traded_at = payload.get("t") if isinstance(payload, dict) else None
    if not last or not traded_at:
        raise ProviderDataError(FINNHUB, f"no quote data for {symbol}")
    return build_quote(
        provider=FINNHUB,
        symbol=symbol,
        asset_class=asset_class,
        quote_grade=quote_grade(FINNHUB, asset_class),
        received_at=received_at,
        raw_payload=payload,
        currency=currency,
        last=last,
        provider_timestamp=datetime.fromtimestamp(traded_at, tz=timezone.utc),
    )
