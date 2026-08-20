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
    provider_timestamp: datetime | None
    received_at: datetime
    raw_payload: dict


def as_decimal(value):
    if value is None or isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def build_quote(provider, symbol, asset_class, quote_grade, received_at, raw_payload,
                currency=None, bid=None, ask=None, last=None, reference_mid=None,
                previous_close=None,
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
        provider_timestamp=provider_timestamp,
        received_at=received_at,
        raw_payload=raw_payload,
    )
