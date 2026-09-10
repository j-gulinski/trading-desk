"""Split validated terms into what the instrument row stores and what trade metadata
keeps, and rebuild the full terms the pricing and trade code consume."""

from dataclasses import dataclass

from desk_domain.instruments import instrument_type_for


@dataclass(frozen=True)
class ContractData:
    terms: dict
    pricing: dict
    opening: dict
    closing: dict

    def metadata(self):
        return {"pricing": self.pricing, "open": self.opening, "close": self.closing}


def split_terms(instrument):
    contract = instrument.contract()
    pricing = instrument.pricing()
    ignored = set(contract) | set(pricing) | set(instrument.derived()) | {
        "asset_class", "currency", "settlement_currency", instrument.underlying_field,
    }
    opening, closing = {}, {}
    for key, value in instrument.extras.items():
        if key.startswith("close_"):
            closing[key.removeprefix("close_")] = value
        elif key not in ignored:
            opening[key] = value
    return ContractData(contract, pricing, opening, closing)


def effective_terms(instrument_type, currency, contract, metadata, underlying_symbol=None):
    pricing = metadata.get("pricing") or {}
    allowed = {spec["name"] for spec in instrument_type.models} or {instrument_type.model}
    name = pricing.get("model") or (contract or {}).get("model") or instrument_type.model
    if name not in allowed:
        raise ValueError(f"unsupported pricing model for {instrument_type.asset_class}")
    data = {
        **(metadata.get("open") or {}),
        **pricing,
        **(contract or {}),
        "model": name,
        "currency": currency,
    }
    data.update({f"close_{key}": value for key, value in (metadata.get("close") or {}).items()})
    if instrument_type.has_field("settlement_currency"):
        data["settlement_currency"] = currency
    if underlying_symbol is not None and instrument_type.underlying_field:
        data[instrument_type.underlying_field] = underlying_symbol
    return instrument_type.from_dict("", data).as_terms()


def trade_terms(trade):
    instrument = trade.instrument
    return effective_terms(
        instrument_type_for(instrument.asset_class), instrument.currency, instrument.terms,
        trade.trade_metadata or {},
        instrument.underlying.symbol if instrument.underlying else None,
    )


def with_close_metadata(metadata, provenance):
    return {**(metadata or {}), "close": {
        key.removeprefix("close_"): value for key, value in provenance.items()
    }}
