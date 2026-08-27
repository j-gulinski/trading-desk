"""Asset-class router used by previews, live valuations and scenarios."""

from pricing_service.pricers.bond import registration as bond
from pricing_service.pricers.european_option import registration as european_option
from pricing_service.pricers.irs import registration as irs
from pricing_service.pricers.spot import registration as spot

REGISTRATIONS = (spot, bond, european_option, irs)


def _by_asset_class(registrations):
    routed = {}
    for registration in registrations:
        for asset_class in registration.asset_classes:
            if asset_class in routed:
                raise ValueError(f"duplicate pricer registration for {asset_class}")
            routed[asset_class] = registration
    return routed


BY_ASSET_CLASS = _by_asset_class(REGISTRATIONS)


def _pricer(asset_class):
    return BY_ASSET_CLASS.get(asset_class)


def market_inputs(asset_class, symbol, meta, provider=None):
    pricer = _pricer(asset_class)
    return {} if pricer is None else pricer.load_inputs(symbol, meta, provider)


def price_from_inputs(asset_class, meta, inputs):
    pricer = _pricer(asset_class)
    return None if pricer is None else pricer.calculate(meta, inputs)


def shock_inputs(asset_class, inputs, shock):
    pricer = _pricer(asset_class)
    return None if pricer is None else pricer.shock_inputs(inputs, shock)


def price_details(asset_class, terms, inputs):
    pricer = _pricer(asset_class)
    return {} if pricer is None else pricer.details(terms, inputs)
