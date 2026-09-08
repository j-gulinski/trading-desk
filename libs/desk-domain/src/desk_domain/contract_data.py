from dataclasses import dataclass

from desk_domain.term_schemas import IRS_PAYMENTS_PER_YEAR
from desk_pricing.provenance import MODEL_NAMES


CONTRACT_FIELDS = {
    "EQUITY": (), "FX": (), "COMMODITY": (),
    "BOND": ("face_value", "coupon_rate", "maturity_years", "payments_per_year"),
    "IRS": ("direction", "notional", "fixed_rate", "maturity_years", "floating_rate_index_tenor"),
    "EUROPEAN_OPTION": ("option_type", "strike", "maturity_years", "multiplier"),
}


@dataclass(frozen=True)
class ContractData:
    terms: dict
    pricing: dict
    opening: dict
    closing: dict

    def metadata(self):
        return {"pricing": self.pricing, "open": self.opening, "close": self.closing}


def split_terms(asset_class, terms):
    contract = {key: terms[key] for key in CONTRACT_FIELDS[asset_class] if key in terms}
    pricing = {"model": MODEL_NAMES[asset_class]}
    for key in ("discount_curve", "volatility"):
        if key in terms:
            pricing[key] = terms[key]
    ignored = set(contract) | set(pricing) | {
        "asset_class", "currency", "settlement_currency", "underlying_symbol",
        "projection_curve", "payments_per_year", "pricing_approach",
    }
    opening, closing = {}, {}
    for key, value in terms.items():
        if key.startswith("close_"):
            closing[key.removeprefix("close_")] = value
        elif key not in ignored:
            opening[key] = value
    return ContractData(contract, pricing, opening, closing)


def effective_terms(asset_class, currency, contract, metadata, underlying_symbol=None):
    pricing = metadata.get("pricing") or {}
    if pricing.get("model") != MODEL_NAMES[asset_class]:
        raise ValueError(f"unsupported pricing model for {asset_class}")
    terms = {**(metadata.get("open") or {}), **pricing, **contract,
             "asset_class": asset_class, "currency": currency}
    terms.update({f"close_{key}": value for key, value in (metadata.get("close") or {}).items()})
    if asset_class in ("BOND", "IRS"):
        terms["settlement_currency"] = currency
    if asset_class == "IRS":
        terms["payments_per_year"] = IRS_PAYMENTS_PER_YEAR[terms["floating_rate_index_tenor"]]
        terms["projection_curve"] = terms["discount_curve"]
        terms["pricing_approach"] = "SINGLE_CURVE_APPROXIMATION"
    if underlying_symbol is not None:
        terms["underlying_symbol"] = underlying_symbol
    return terms


def trade_terms(trade):
    instrument = trade.instrument
    return effective_terms(
        instrument.asset_class, instrument.currency, instrument.terms,
        trade.trade_metadata or {},
        instrument.underlying.symbol if instrument.underlying else None,
    )


def with_close_metadata(metadata, provenance):
    return {**(metadata or {}), "close": {
        key.removeprefix("close_"): value for key, value in provenance.items()
    }}
