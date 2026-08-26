from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, DecimalException
from enum import Enum

from shared.freshness import QuoteGrade


class PriceBasis(str, Enum):
    BID_ASK = "BID_ASK"
    LAST = "LAST"
    REFERENCE_MID = "REFERENCE_MID"


@dataclass(frozen=True)
class NormalizedQuote:
    provider: str
    symbol: str
    asset_class: str
    currency: str | None
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    mid: Decimal
    price_basis: PriceBasis
    quote_grade: QuoteGrade
    previous_close: Decimal | None
    provider_timestamp: datetime | None
    received_at: datetime
    raw_payload: dict


WIRE_QUOTE_FIELDS = (
    "provider",
    "symbol",
    "asset_class",
    "currency",
    "bid",
    "ask",
    "last",
    "mid",
    "price_basis",
    "quote_grade",
    "previous_close",
    "provider_timestamp",
    "received_at",
)


def quote_market(symbol, asset_class, raw_payload=None):
    """Return an actual trading venue when the symbol or provider identifies one."""
    normalized_class = str(asset_class or "").upper()
    if normalized_class in ("FX", "COMMODITY"):
        return "OTC"
    if normalized_class != "EQUITY":
        return None

    raw_payload = raw_payload if isinstance(raw_payload, dict) else {}
    exchange = raw_payload.get("exchange")
    if isinstance(exchange, str):
        exchange = exchange.strip()
        if exchange and exchange.upper() not in ("US", "USA", "UNITED STATES"):
            return exchange.upper()

    if isinstance(symbol, str):
        _, separator, venue = symbol.rpartition(":")
        if separator and venue:
            return venue.upper()
    return None


def quote_name(symbol, raw_payload=None):
    """Return provider instrument identity without treating the ticker as its name."""
    raw_payload = raw_payload if isinstance(raw_payload, dict) else {}
    for field in ("name", "instrument_name", "description"):
        value = raw_payload.get(field)
        if (
            isinstance(value, str)
            and value.strip()
            and value.strip().upper() != str(symbol).upper()
        ):
            return value.strip()
    return None


def wire_quote_fields(quote):
    return {field: getattr(quote, field) for field in WIRE_QUOTE_FIELDS}


def wire_tick(quote, classifier, origin=None, reference=False):
    """One published quote: the wire fields, its freshness classifier and why it is watched."""
    origin = origin or {}
    return {
        **wire_quote_fields(quote),
        "name": quote_name(quote.symbol, quote.raw_payload),
        "market": quote_market(quote.symbol, quote.asset_class, quote.raw_payload),
        "event_time": quote.received_at,
        **classifier,
        "watched": bool(origin.get("watched")),
        "held": bool(origin.get("held")),
        "benchmark": bool(origin.get("benchmark")),
        "reference": reference,
    }


def as_decimal(value):
    if value is None or isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _positive_decimal(value, field):
    try:
        number = as_decimal(value)
    except (DecimalException, TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if number is not None and (not number.is_finite() or number <= 0):
        raise ValueError(f"{field} must be finite and greater than zero")
    return number


def build_quote(provider, symbol, asset_class, quote_grade, received_at, raw_payload,
                currency=None, bid=None, ask=None, last=None, reference_mid=None,
                previous_close=None, provider_timestamp=None):
    bid = _positive_decimal(bid, "bid")
    ask = _positive_decimal(ask, "ask")
    last = _positive_decimal(last, "last")
    reference_mid = _positive_decimal(reference_mid, "reference_mid")
    previous_close = _positive_decimal(previous_close, "previous_close")

    if bid is not None and ask is not None and bid > ask:
        raise ValueError("bid cannot be greater than ask")

    if bid is not None and ask is not None:
        price_basis = PriceBasis.BID_ASK
        mid = (bid + ask) / 2
    elif reference_mid is not None:
        price_basis = PriceBasis.REFERENCE_MID
        mid = reference_mid
    elif last is not None:
        price_basis = PriceBasis.LAST
        mid = last
    else:
        raise ValueError(f"quote for {symbol} from {provider} carries no price")

    return NormalizedQuote(
        provider=provider,
        symbol=symbol,
        asset_class=asset_class,
        currency=currency,
        bid=bid,
        ask=ask,
        last=last,
        mid=mid,
        price_basis=price_basis,
        quote_grade=quote_grade,
        previous_close=previous_close,
        provider_timestamp=provider_timestamp,
        received_at=received_at,
        raw_payload=raw_payload,
    )
