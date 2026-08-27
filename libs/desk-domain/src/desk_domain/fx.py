from decimal import Context, Decimal

from desk_runtime.db import session_scope
from desk_domain.models import MarketDataSpotPrice
from desk_domain.providers import ECB, NBP, OFFICIAL_FIXING_PROVIDERS

_RATE_DIGITS = Context(prec=8)


def load_official_rates(session=None):
    def read(active_session):
        rows = (
            active_session.query(
                MarketDataSpotPrice.provider,
                MarketDataSpotPrice.symbol,
                MarketDataSpotPrice.mid,
                MarketDataSpotPrice.provider_timestamp,
            )
            .filter(
                MarketDataSpotPrice.provider.in_(OFFICIAL_FIXING_PROVIDERS),
                MarketDataSpotPrice.asset_class == "FX",
            )
            .all()
        )
        return [
            (provider, symbol, Decimal(str(mid)), timestamp.date())
            for provider, symbol, mid, timestamp in rows
            if timestamp is not None and len(symbol) == 6
        ]

    if session is None:
        with session_scope() as owned:
            extracted = read(owned)
    else:
        extracted = read(session)

    rates = {provider: {} for provider in OFFICIAL_FIXING_PROVIDERS}
    for provider, symbol, mid, as_of in extracted:
        rates[provider][symbol] = (mid, as_of)
    return rates


def known_currencies(rates):
    currencies = set()
    for table in rates.values():
        for symbol in table:
            currencies.add(symbol[:3])
            currencies.add(symbol[3:])
    return currencies


def _resolution(rate, path, provider, as_of, symbols):
    return {
        "rate": _RATE_DIGITS.plus(rate),
        "path": path,
        "provider": provider,
        "as_of": as_of,
        "symbols": symbols,
        "reason": None,
    }


def _direct(rates, from_ccy, to_ccy):
    candidates = []
    for provider in OFFICIAL_FIXING_PROVIDERS:
        table = rates.get(provider, {})
        symbol = f"{from_ccy}{to_ccy}"
        if symbol in table:
            mid, as_of = table[symbol]
            candidates.append((as_of, provider == ECB, provider, symbol, mid, False))
        inverse = f"{to_ccy}{from_ccy}"
        if inverse in table:
            mid, as_of = table[inverse]
            candidates.append((as_of, provider == ECB, provider, inverse, mid, True))
    if not candidates:
        return None
    as_of, _, provider, symbol, mid, inverted = max(candidates)
    rate = Decimal(1) / mid if inverted else mid
    return _resolution(rate, f"{from_ccy}→{to_ccy}", provider, as_of, [symbol])


def _cross(rates, from_ccy, to_ccy, provider, leg_of, hub):
    table = rates.get(provider, {})
    from_leg = table.get(leg_of(from_ccy))
    to_leg = table.get(leg_of(to_ccy))
    if from_leg is None or to_leg is None:
        return None
    if provider == ECB:
        rate = to_leg[0] / from_leg[0]
    else:
        rate = from_leg[0] / to_leg[0]
    return _resolution(
        rate,
        f"{from_ccy}→{to_ccy} via {hub}",
        provider,
        min(from_leg[1], to_leg[1]),
        [leg_of(from_ccy), leg_of(to_ccy)],
    )


def resolve_rate(from_ccy, to_ccy, rates):
    if from_ccy == to_ccy:
        return _resolution(Decimal(1), from_ccy, None, None, [])
    resolution = (
        _direct(rates, from_ccy, to_ccy)
        or _cross(rates, from_ccy, to_ccy, ECB, lambda c: f"EUR{c}", "EUR")
        or _cross(rates, from_ccy, to_ccy, NBP, lambda c: f"{c}PLN", "PLN")
    )
    if resolution is not None:
        return resolution
    return {
        "rate": None,
        "path": None,
        "provider": None,
        "as_of": None,
        "symbols": [],
        "reason": f"no official {from_ccy}→{to_ccy} rate is published",
    }


def convert(amount, from_ccy, to_ccy, rates=None):
    if rates is None:
        rates = load_official_rates()
    resolution = resolve_rate(from_ccy, to_ccy, rates)
    converted = (
        Decimal(str(amount)) * resolution["rate"]
        if resolution["rate"] is not None else None
    )
    return {**resolution, "from": from_ccy, "to": to_ccy, "converted": converted}


def rates_to(to_ccy, rates=None):
    if rates is None:
        rates = load_official_rates()
    return {
        currency: resolve_rate(currency, to_ccy, rates)
        for currency in sorted(known_currencies(rates) | {to_ccy})
    }
