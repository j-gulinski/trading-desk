from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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
    day_open: Decimal | None
    day_high: Decimal | None
    day_low: Decimal | None
    week52_high: Decimal | None
    week52_low: Decimal | None
    volume: Decimal | None
    average_volume: Decimal | None
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
    "day_open",
    "day_high",
    "day_low",
    "week52_high",
    "week52_low",
    "volume",
    "average_volume",
    "provider_timestamp",
    "received_at",
)


def wire_quote_fields(quote):
    return {field: getattr(quote, field) for field in WIRE_QUOTE_FIELDS}


def as_decimal(value):
    if value is None or isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def build_quote(provider, symbol, asset_class, quote_grade, received_at, raw_payload,
                currency=None, bid=None, ask=None, last=None, reference_mid=None,
                previous_close=None, day_open=None, day_high=None, day_low=None,
                week52_high=None, week52_low=None, volume=None, average_volume=None,
                provider_timestamp=None):
    bid = as_decimal(bid)
    ask = as_decimal(ask)
    last = as_decimal(last)
    reference_mid = as_decimal(reference_mid)

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
        previous_close=as_decimal(previous_close),
        day_open=as_decimal(day_open),
        day_high=as_decimal(day_high),
        day_low=as_decimal(day_low),
        week52_high=as_decimal(week52_high),
        week52_low=as_decimal(week52_low),
        volume=as_decimal(volume),
        average_volume=as_decimal(average_volume),
        provider_timestamp=provider_timestamp,
        received_at=received_at,
        raw_payload=raw_payload,
    )
